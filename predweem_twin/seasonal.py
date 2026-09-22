"""Referencias descriptivas locales y progreso causal del reservorio San Pedro."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd


LOCAL_CAMPAIGNS = {
    2025: "models/modelo_clusters_k3.pkl",
    2026: "data/calibration/san_pedro_2026_counts.csv",
}


def load_seasonal_reference(source: str | Path, as_of=None) -> pd.DataFrame:
    """Carga curvas completas sin utilizar cierres posteriores al corte.

    Cada campaña aporta el mismo peso. El rango es mínimo–máximo observado,
    no un intervalo probabilístico. Las curvas son contexto descriptivo y no
    intervienen en el denominador del porcentaje calculado por el motor.
    """
    source = Path(source)
    manifest = json.loads(source.read_text(encoding="utf-8"))
    if manifest.get("site") != "San Pedro":
        raise ValueError("La referencia debe corresponder a San Pedro.")
    local = []
    for item in manifest["campaigns"]:
        year = item["year"]
        # Una campaña nueva no se agrega al pool por aparecer en el archivo.
        if year not in LOCAL_CAMPAIGNS:
            continue
        if (item.get("site", manifest["site"]) != "San Pedro"
                or item.get("source") != LOCAL_CAMPAIGNS[year]
                or (year == 2025 and item.get("source_curve")
                    != "emrel sp 2025 san pedro.xlsx")):
            raise ValueError(f"Procedencia local inválida para San Pedro {year}.")
        local.append(item)
    if sorted(item["year"] for item in local) != [2025, 2026]:
        raise ValueError("Se requiere una única referencia de San Pedro 2025 y 2026.")
    data_path = source.parent / manifest["curves_file"]
    if sha256(data_path.read_bytes()).hexdigest() != manifest["curves_sha256"]:
        raise ValueError("Las curvas estacionales no coinciden con su procedencia.")
    frame = pd.read_csv(data_path)
    cutoff = pd.Timestamp(as_of).normalize() if as_of is not None else None
    campaigns = [
        item for item in sorted(local, key=lambda item: item["year"])
        if item["complete"] and (
            cutoff is None or max(
                pd.Timestamp(item["available_from"]),
                pd.Timestamp(item.get("observations_end", item["available_from"])),
            ) <= cutoff
        )
    ]
    if not campaigns:
        raise ValueError("No hay campañas completas disponibles para esta fecha.")
    reference = pd.DataFrame({"Julian_days": np.arange(1, 366)})
    for item in campaigns:
        year = item["year"]
        curve = frame.loc[frame["Campana"].eq(year)].sort_values("Julian_days")
        if not np.array_equal(curve["Julian_days"], reference["Julian_days"]):
            raise ValueError(f"Eje diario incompleto o duplicado en {year}.")
        values = curve["Progreso"].to_numpy(float)
        valid = values[np.isfinite(values)]
        if (len(valid) == 0 or (valid < 0).any() or (valid > 1).any()
                or (np.diff(valid) < -1e-12).any() or not np.isclose(valid[-1], 1)):
            raise ValueError(f"Progreso estacional inválido en {year}.")
        reference[f"Progreso_{year}"] = values
    columns = [f"Progreso_{item['year']}" for item in campaigns]
    reference["Progreso_Min"] = reference[columns].min(axis=1)
    reference["Progreso_Mediano"] = reference[columns].median(axis=1)
    reference["Progreso_Max"] = reference[columns].max(axis=1)
    reference["N_Campanas_Dia"] = reference[columns].notna().sum(axis=1)
    reference["N_Campanas"] = len(campaigns)
    reference["Campanas"] = ", ".join(str(item["year"]) for item in campaigns)
    reference["Campanas_Anos"] = reference["Campanas"]
    reference["Campanas_Excluidas"] = (
        "Todas las localidades y campañas excepto San Pedro 2025 y San Pedro 2026"
        + ("; San Pedro 2026 no disponible al corte" if len(campaigns) == 1 else "")
    )
    reference.attrs["campaigns"] = campaigns
    return reference


def reference_calendar_days(dates) -> np.ndarray:
    """Alinea por mes/día; el 29/02 se sitúa entre el 28/02 y el 01/03."""
    dates = pd.DatetimeIndex(pd.to_datetime(dates))
    days = dates.dayofyear.to_numpy(dtype=float)
    days -= (dates.is_leap_year & (dates.month > 2)).astype(int)
    days[(dates.month == 2) & (dates.day == 29)] = 59.5
    return days


def reference_progress(reference: pd.DataFrame, calendar_days):
    """Interpola mínimo, mediana y máximo, conservando tramos desconocidos."""
    return tuple(np.interp(
        np.asarray(calendar_days, dtype=float), reference["Julian_days"],
        reference[column], left=np.nan, right=np.nan,
    ) for column in ("Progreso_Min", "Progreso_Mediano", "Progreso_Max"))


def cohort_progress(trajectory: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Fracción liberada y remanente del reservorio inicial unitario.

    EMERREL ya es masa liberada por el motor SP-FINAL. No se divide por el
    total observado al cierre ni por un progreso histórico en la fecha actual.
    El reservorio es un estado modelado, no una medición del banco de semillas.
    """
    released = trajectory["EMERAC"].to_numpy(float)
    remaining = (trajectory["Reserva_Cohorte"] - trajectory["EMERREL"]).to_numpy(float)
    if (not np.isfinite(released).all() or not np.isfinite(remaining).all()
            or (released < -1e-10).any() or (remaining < -1e-10).any()
            or not np.allclose(released + remaining, 1.0, atol=1e-10, rtol=0)):
        raise ValueError("El reservorio de cohorte no conserva su masa inicial.")
    return np.clip(released, 0, 1), np.clip(remaining, 0, 1)
