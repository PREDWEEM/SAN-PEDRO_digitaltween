"""Genera un perfil por sitio y diagnósticos reproducibles sin entrenar la ANN.

Desde la raíz: python scripts/calibrate_site.py
Los CSV de entrada son copias fijas; no se consulta meteorología en vivo.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from predweem_twin.calibration import (  # noqa: E402
    calibrated_progress, fit_site_calibration, model_fingerprint,
)
from predweem_twin.core import ModelParameters, PracticalANNModel, run_predweem  # noqa: E402
from predweem_twin.seasonal import load_seasonal_reference  # noqa: E402
from predweem_twin.weather import read_weather_file, forecast_mask  # noqa: E402


def read_site_counts(path):
    """Lee fecha + plantas sin convertir a densidad ni inferir repeticiones.

    El campo interno Flujo_observado_PLM2 se conserva sólo como adaptador a
    la API común de ajuste; sus valores mantienen la escala original.
    """
    path = Path(path)
    raw = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    if list(raw.columns) != ["fecha", "plantas"]:
        raise ValueError("Se requieren las columnas originales fecha y plantas.")
    prepared = pd.DataFrame({
        "Fecha": pd.to_datetime(raw["fecha"], errors="raise"),
        "Flujo_observado_PLM2": pd.to_numeric(raw["plantas"], errors="raise"),
    })
    if prepared.Fecha.isna().any() or prepared.Fecha.duplicated().any():
        raise ValueError("Fechas inválidas o duplicadas en los conteos.")
    return raw, prepared.sort_values("Fecha").reset_index(drop=True), {}


def build_calibration(observations_path, weather_path, output_path, site="San Pedro",
                      coverage=ModelParameters().cobertura_pct, w_max=ModelParameters().w_max, source_metadata_path=None):
    observations_path, weather_path, output_path = map(
        Path, (observations_path, weather_path, output_path)
    )
    source_metadata = {}
    if source_metadata_path:
        source_metadata = json.loads(Path(source_metadata_path).read_text(encoding="utf-8"))
    raw, prepared, import_metadata = read_site_counts(observations_path)
    raw = raw.dropna(axis=1, how="all").dropna(axis=0, how="all")
    date_column = next((column for column in raw if str(column).strip().lower() == "fecha"), None)
    if date_column is None:
        raise ValueError("El archivo requiere la columna FECHA.")
    sample_dates = pd.to_datetime(raw[date_column], errors="raise")
    if sample_dates.isna().any() or sample_dates.duplicated().any():
        raise ValueError("Las fechas de muestreo deben ser válidas y únicas.")
    weather = read_weather_file(weather_path)
    weather["Fecha"] = pd.to_datetime(weather["Fecha"], errors="raise")
    last_count = sample_dates.max()
    weather = weather.loc[weather["Fecha"] <= last_count].copy()
    if forecast_mask(weather).any():
        raise ValueError("La calibración histórica no admite filas de pronóstico.")
    model = PracticalANNModel.from_directory(ROOT / "models")
    reference = load_seasonal_reference(
        ROOT / "models/modelo_clusters_k3.pkl", excluded_years=("2010", "2015"), include_patterns=("san pedro",),
    )
    parameters = ModelParameters(cobertura_pct=coverage, w_max=w_max)

    def simulate(cutoff, end=None):
        return run_predweem(
            weather.loc[weather["Fecha"] <= (end if end is not None else cutoff)],
            model, parameters, normalization_as_of=cutoff, seasonal_reference=reference,
        )

    trajectory = simulate(last_count)
    profile, comparison = fit_site_calibration(trajectory, prepared, site=site)

    # Mantener los cortes de una revisión previa cuando están registrados,
    # aunque se agregue una fecha inicial. Sólo conteos y meteorología hasta el
    # corte entran al ajuste. Para evaluar el intervalo siguiente se usa su
    # meteorología realizada: es un hindcast condicional, no pronóstico archivado.
    holdout_rows = []
    validation_cutoffs = source_metadata.get("validation_cutoffs")
    if validation_cutoffs:
        counts = []
        for value in validation_cutoffs:
            cutoff = pd.Timestamp(value)
            matches = prepared.index[prepared["Fecha"].eq(cutoff)].tolist()
            if not matches or matches[0] < 6 or matches[0] + 1 >= len(prepared):
                raise ValueError(f"Corte de evaluación no disponible: {value}")
            counts.append(matches[0] + 1)
    else:
        counts = range(7, len(prepared))
    for count in counts:
        training = prepared.iloc[:count].copy()
        cutoff = pd.Timestamp(training["Fecha"].iloc[-1])
        target = prepared.iloc[count]
        target_date = pd.Timestamp(target["Fecha"])
        fitted, _ = fit_site_calibration(simulate(cutoff), training, site=site)
        evaluation = simulate(cutoff, end=target_date).set_index("Fecha")
        endpoints = evaluation.loc[[cutoff, target_date], "EMERAC_NORMALIZADA"].to_numpy(float)
        base = float(np.diff(endpoints)[0] * fitted["fit"]["nuisance_scale_base"])
        calibrated = float(np.diff(calibrated_progress(
            endpoints, **fitted["parameters"]
        ))[0] * fitted["fit"]["nuisance_scale_calibrated"])
        holdout_rows.append({
            "Corte_entrenamiento": cutoff.date().isoformat(),
            "Fecha_evaluacion": target_date.date().isoformat(),
            "Dias_intervalo": int((target_date - cutoff).days),
            "N_muestreos_ajuste": count,
            "Observado_Unidades": float(target["Flujo_observado_PLM2"]),
            "Base_Unidades": base,
            "Calibrado_Unidades": calibrated,
            "Offset": fitted["parameters"]["offset"],
            "Slope": fitted["parameters"]["slope"],
        })
    holdout = pd.DataFrame(holdout_rows)
    validation = {
        "kind": "evaluacion_retrospectiva_capa_con_motor_precalibrado_2025_2026",
        "independent_season": False,
        "base_model_uses_training_season": True,
        "n_intervals": len(holdout),
        "note": (
            "Ajuste con datos hasta cada corte y evaluación del siguiente intervalo. "
            "El motor base ya fue calibrado con 2025 y 2026: esta evaluación de la capa adicional no es independiente. Se utiliza SIGA y ECMWF realizado, "
            "no la emisión de pronóstico disponible en cada corte. No demuestra "
            "transferencia a otra campaña ni precisión operativa a siete días."
        ),
    }
    if not holdout.empty:
        y = holdout["Observado_Unidades"].to_numpy()
        validation.update({
            "rmse_base_units": float(np.sqrt(np.mean((holdout["Base_Unidades"].to_numpy() - y)**2))),
            "rmse_calibrated_units": float(np.sqrt(np.mean((holdout["Calibrado_Unidades"].to_numpy() - y)**2))),
            "intervals_improved": int((
                (holdout["Calibrado_Unidades"] - y).abs()
                < (holdout["Base_Unidades"] - y).abs()
            ).sum()),
        })
    first_date = pd.Timestamp(prepared["Fecha"].iloc[0]).date().isoformat()
    initial_zero = bool(prepared["Flujo_observado_PLM2"].iloc[0] == 0)
    initial_note = (
        f"El registro inicial de cero del {first_date} delimita el primer intervalo; "
        "no se infiere ausencia de emergencia en fechas anteriores."
        if initial_zero else
        "Primer conteo conservado pero excluido del ajuste: inicio del intervalo desconocido."
    )
    profile.update({
        "observations_start": first_date,
        "initial_zero_reference": initial_zero,
        "model_fingerprint": model_fingerprint(ROOT),
        "model_parameters": asdict(parameters),
        "seasonal_reference": {
            "include_patterns": ["san pedro"],
            "excluded_years": ["2010", "2015"],
            "scope": "Referencia local San Pedro 2025; una campaña",
            "n_campaigns": int(reference["N_Campanas"].iloc[0]),
            "campaigns": reference["Campanas"].iloc[0],
        },
        "source": {
            **source_metadata,
            "observations_file": observations_path.name,
            "observations_sha256": sha256(observations_path.read_bytes()).hexdigest(),
            "weather_file": weather_path.name,
            "weather_sha256": sha256(weather_path.read_bytes()).hexdigest(),
            "weather_types": weather["TipoDato"].value_counts().to_dict() if "TipoDato" in weather else {},
            "observed_total_units": float(prepared["Flujo_observado_PLM2"].sum()),
            "replicate_count": import_metadata.get("n_repeticiones"),
            "replicate_conversion_factor": import_metadata.get("factor_conversion_repeticiones"),
        },
        "validation": validation,
        "limitations": [
            "Una sola campaña incompleta. No se estima ni transfiere un total estacional.",
            initial_note,
            f"Cobertura de {coverage:g} % y Wmax de {w_max:g} mm son supuestos de la configuración operativa; el archivo no informa manejo ni cobertura.",
            "El archivo fecha + plantas no informa superficie ni repeticiones. Se mantiene su escala sin convertir a plantas/m². Se utiliza un piso de ponderación común, no un error de muestreo medido.",
            "Se conserva SP-FINAL-2025-2026: interacción termohídrica continua y reservorio causal de cohorte con parámetros originales congelados.",
            "La referencia local sólo incluye San Pedro 2025; sus percentiles no caracterizan robustamente la variabilidad anual. El motor base ya fue calibrado con 2025 y 2026; los datos no constituyen evidencia independiente.",
            "La meteorología del ajuste incluye 193 días SIGA observados y tres provisionales ECMWF (9–11 de junio); no se ocultan esos huecos de estación.",
            "La transformación no crea cohortes en fechas bloqueadas por el motor biofísico.",
            "Un parámetro en su límite indica que persisten diferencias estructurales.",
            "El ajuste no reduce automáticamente la incertidumbre de asimilación.",
            "Los gráficos de la campaña de ajuste son retrospectivos, no predicciones independientes.",
        ],
    })
    # Cambiar la identidad aun si una revisión conserva la última fecha.
    input_signature = sha256(json.dumps({
        "observations": profile["source"]["observations_sha256"],
        "weather": profile["source"]["weather_sha256"],
        "model": profile["model_fingerprint"],
        "parameters": profile["model_parameters"],
        "seasonal_reference": profile["seasonal_reference"],
        "method": profile["method"],
        "calibration_parameters": profile["parameters"],
    }, sort_keys=True).encode()).hexdigest()
    profile["profile_id"] += "-" + input_signature[:10]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    comparison.to_csv(output_path.with_name(output_path.stem + "_fit.csv"), index=False, date_format="%Y-%m-%d")
    holdout.to_csv(output_path.with_name(output_path.stem + "_holdout.csv"), index=False)
    print(json.dumps({"profile": profile["profile_id"], "fit": profile["fit"], "validation": validation}, indent=2))
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, default=ROOT / "data/calibration/san_pedro_2026_counts.csv")
    parser.add_argument("--weather", type=Path, default=ROOT / "data/calibration/san_pedro_2026_weather.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/calibration/san_pedro_2026.json")
    parser.add_argument("--source-metadata", type=Path, default=ROOT / "data/calibration/san_pedro_2026_source.json")
    parser.add_argument("--site", default="San Pedro")
    parser.add_argument("--coverage", type=float, default=ModelParameters().cobertura_pct)
    parser.add_argument("--w-max", type=float, default=ModelParameters().w_max)
    args = parser.parse_args()
    build_calibration(args.observations, args.weather, args.output, args.site,
                      args.coverage, args.w_max, args.source_metadata)


if __name__ == "__main__":
    main()
