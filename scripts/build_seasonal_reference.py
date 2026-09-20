"""Genera las referencias 2025–2026 desde fuentes locales inmutables, sin red."""

from hashlib import sha256
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def build_reference(output_dir=None):
    target = Path(output_dir) if output_dir else ROOT / "data/reference"
    target.mkdir(parents=True, exist_ok=True)
    classifier = ROOT / "models/modelo_clusters_k3.pkl"
    counts_file = ROOT / "data/calibration/san_pedro_2026_counts.csv"
    with classifier.open("rb") as handle:
        payload = pickle.load(handle)
    selected = [i for i, name in enumerate(payload["names"])
                if str(name).lower() == "emrel sp 2025 san pedro.xlsx"]
    if len(selected) != 1:
        raise ValueError("Se requiere una única curva local San Pedro 2025.")
    days = np.asarray(payload["JD_common"], dtype=float)
    flow = np.asarray(payload["curves_interp"][selected[0]], dtype=float)
    if (not np.isfinite(flow).all() or (flow < 0).any() or flow.sum() <= 0
            or len(days) != len(flow) or (np.diff(days) <= 0).any()):
        raise ValueError("Curva procesada 2025 inválida.")
    axis = np.arange(1, 366)
    progress_2025 = np.interp(axis, days, np.cumsum(flow) / flow.sum(), left=np.nan, right=1)
    counts = pd.read_csv(counts_file, parse_dates=["fecha"])
    dates = counts["fecha"]
    values = counts["plantas"].to_numpy(float)
    if (dates.isna().any() or dates.duplicated().any()
            or not dates.is_monotonic_increasing or not dates.dt.year.eq(2026).all()
            or not np.isfinite(values).all() or (values < 0).any()
            or values.sum() <= 0 or values[0] != 0):
        raise ValueError("Conteos 2026 inválidos o sin cero inicial delimitador.")
    # Interpolación del acumulado, NO de los conteos por intervalo. Conserva
    # cada masa entre dos muestreos. La ubicación diaria interna es desconocida.
    progress_2026 = np.interp(axis, dates.dt.dayofyear, np.cumsum(values) / values.sum(), left=np.nan, right=1)
    output = pd.concat([
        pd.DataFrame({"Campana": year, "Julian_days": axis, "Progreso": np.clip(progress, 0, 1)})
        for year, progress in [(2025, progress_2025), (2026, progress_2026)]
    ], ignore_index=True)
    curves_file = target / "san_pedro_2025_2026_curves.csv"
    output.to_csv(curves_file, index=False, float_format="%.15g", na_rep="")
    manifest = {
        "schema_version": 1,
        "site": "San Pedro",
        "curves_file": curves_file.name,
        "curves_sha256": sha256(curves_file.read_bytes()).hexdigest(),
        "role": "referencias descriptivas; no determinan el porcentaje modelado",
        "complete_seasons_basis": "El usuario declara completas las campañas 2025 y 2026 el 20/09/2026.",
        "bands": "mínimo y máximo de las campañas disponibles; no intervalos de confianza",
        "campaigns": [
            {
                "year": 2025, "complete": True, "available_from": "2026-01-01",
                "source": "models/modelo_clusters_k3.pkl",
                "source_sha256": sha256(classifier.read_bytes()).hexdigest(),
                "source_curve": payload["names"][selected[0]],
                "representation": "flujo diario previamente interpolado y normalizado del clasificador original",
                "source_day_start": int(days[0]), "source_day_end": int(days[-1]),
                "source_daily_points": len(days),
                "processing": "suma acumulada del flujo procesado dividida por su suma total",
                "limitation": "No se dispone aquí de los conteos ni la meteorología originales de 2025; no se reconstruyen densidades.",
            },
            {
                "year": 2026, "complete": True, "available_from": str(dates.max().date()),
                "source": "data/calibration/san_pedro_2026_counts.csv",
                "source_sha256": sha256(counts_file.read_bytes()).hexdigest(),
                "representation": "conteos de plantas por intervalo en la escala del adjunto",
                "observations_start": str(dates.min().date()),
                "observations_end": str(dates.max().date()),
                "sample_count": len(counts), "total_source_units": float(values.sum()),
                "density_units_confirmed": False,
                "processing": "acumulado en muestreos / total registrado; interpolación lineal entre muestreos",
                "limitation": "Sin datos anteriores al cero del 01/02; cierre completo aceptado por declaración del usuario. No se agregan conteos después del 15/07 ni se infieren m².",
            },
        ],
        "limitations": [
            "Dos campañas describen variación observada, sin estimar probabilidades robustas.",
            "La referencia 2025 proviene de un procesamiento previo; 2026 conserva acumulados de conteos por intervalo. La comparación es descriptiva.",
            "No se imputan observaciones nuevas: el valor uno se mantiene tras el cierre declarado de cada campaña.",
            "La exclusión de curvas cerradas después del corte evita mostrar datos futuros. Las revisiones retrospectivas y el motor calibrado con 2025–2026 no constituyen pronósticos históricos independientes.",
        ],
    }
    (target / "san_pedro_2025_2026.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    result = build_reference()
    print("Referencias generadas:", [item["year"] for item in result["campaigns"]])
