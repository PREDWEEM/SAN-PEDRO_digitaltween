from pathlib import Path
import pickle

import numpy as np
import pandas as pd
import pytest

from predweem_twin.core import ModelParameters, PracticalANNModel, run_predweem
from predweem_twin.seasonal import load_seasonal_reference, reference_calendar_days
from scripts.build_seasonal_reference import build_reference

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "data/reference/san_pedro_2025_2026.json"


def simulate(weather, cutoff="2026-03-30", reference=None):
    return run_predweem(
        weather, PracticalANNModel.from_directory(ROOT / "models"), ModelParameters(),
        normalization_as_of=cutoff, seasonal_reference=reference,
    )


def test_complete_campaigns_preserve_their_sources_and_equal_weight():
    reference = load_seasonal_reference(SOURCE)
    assert reference.N_Campanas.eq(2).all()
    assert reference.Campanas.eq("2025, 2026").all()
    with (ROOT / "models/modelo_clusters_k3.pkl").open("rb") as handle:
        payload = pickle.load(handle)
    index = payload["names"].index("emrel sp 2025 san pedro.xlsx")
    flow = np.asarray(payload["curves_interp"][index])
    np.testing.assert_allclose(reference.Progreso_2025.iloc[:len(flow)], np.cumsum(flow) / flow.sum())
    counts = pd.read_csv(ROOT / "data/calibration/san_pedro_2026_counts.csv", parse_dates=["fecha"])
    actual = reference.set_index("Julian_days").loc[counts.fecha.dt.dayofyear, "Progreso_2026"]
    np.testing.assert_allclose(actual, counts.plantas.cumsum() / counts.plantas.sum())
    # El acumulado y la masa en cada intervalo son exactamente los del adjunto.
    np.testing.assert_allclose(np.diff(actual), counts.plantas.iloc[1:] / counts.plantas.sum(), atol=1e-14)
    assert reference.Progreso_2026.iloc[:31].isna().all()
    assert reference.Progreso_2026.iloc[195:].eq(1).all()
    both = reference.iloc[31:]
    np.testing.assert_allclose(both.Progreso_Mediano, (both.Progreso_2025 + both.Progreso_2026) / 2)
    np.testing.assert_allclose(both.Progreso_Min, np.minimum(both.Progreso_2025, both.Progreso_2026))
    np.testing.assert_allclose(both.Progreso_Max, np.maximum(both.Progreso_2025, both.Progreso_2026))


def test_reference_excludes_campaigns_closed_after_cutoff():
    early = load_seasonal_reference(SOURCE, as_of="2026-04-05")
    assert early.N_Campanas.eq(1).all()
    assert "Progreso_2026" not in early
    assert load_seasonal_reference(SOURCE, as_of="2026-07-15").N_Campanas.eq(2).all()
    with pytest.raises(ValueError, match="No hay campañas"):
        load_seasonal_reference(SOURCE, as_of="2025-06-01")


def test_reference_rebuild_is_reproducible_and_corruption_is_rejected(tmp_path):
    build_reference(tmp_path)
    for path in SOURCE.parent.iterdir():
        assert (tmp_path / path.name).read_bytes() == path.read_bytes()
    curves = tmp_path / "san_pedro_2025_2026_curves.csv"
    curves.write_text(curves.read_text() + "\n")
    with pytest.raises(ValueError, match="procedencia"):
        load_seasonal_reference(tmp_path / SOURCE.name)


def test_percentage_is_released_mass_and_does_not_follow_historical_calendar():
    weather = pd.read_csv(ROOT / "meteo_daily.csv").iloc[:96]
    reference = load_seasonal_reference(SOURCE, as_of="2026-03-30")
    result = simulate(weather, reference=reference)
    np.testing.assert_allclose(result.EMERAC_NORMALIZADA, result.EMERAC)
    np.testing.assert_allclose(result.EMERAC_NORMALIZADA + result.Reserva_Cohorte_Remanente, 1)
    at_cutoff = result.loc[result.Fecha.eq("2026-03-30")].iloc[0]
    assert not np.isclose(at_cutoff.EMERAC_NORMALIZADA, at_cutoff.Progreso_Estacional_Referencia)
    assert result.EMERAC_NORMALIZADA.iloc[-1] < 1
    altered_reference = reference.copy()
    altered_reference[["Progreso_Min", "Progreso_Mediano", "Progreso_Max"]] = .15
    changed = simulate(weather, reference=altered_reference)
    np.testing.assert_array_equal(result.EMERAC_NORMALIZADA, changed.EMERAC_NORMALIZADA)


def test_percentage_is_causal_when_horizon_cutoff_and_future_weather_change():
    weather = pd.read_csv(ROOT / "meteo_daily.csv")
    short = simulate(weather.iloc[:89], cutoff="2026-03-30")
    long = simulate(weather, cutoff="2026-07-15")
    np.testing.assert_allclose(short.EMERAC_NORMALIZADA, long.EMERAC_NORMALIZADA.iloc[:89], atol=1e-14, rtol=0)
    weather.loc[weather.index[89:], "Prec"] = 100
    changed = simulate(weather)
    np.testing.assert_allclose(short.EMERAC_NORMALIZADA, changed.EMERAC_NORMALIZADA.iloc[:89], atol=1e-14, rtol=0)
    # El tramo sin señal sigue en cero aunque el horizonte incluya el primer pulso.
    before_peak = np.flatnonzero(long.Primer_Pico_Habilitado)[0]
    zero = simulate(weather.iloc[:before_peak])
    assert zero.EMERAC_NORMALIZADA.eq(0).all()
    assert zero.Reserva_Cohorte_Remanente.eq(1).all()


def test_weather_changes_percentage_at_same_date_without_artificial_completion():
    weather = pd.read_csv(ROOT / "meteo_daily.csv").iloc[:96]
    wet = simulate(weather)
    dry_weather = weather.copy()
    dry_weather["Prec"] = 0
    dry = simulate(dry_weather)
    assert wet.EMERAC_NORMALIZADA.iloc[-1] > .1
    assert dry.EMERAC_NORMALIZADA.eq(0).all()
    assert dry.Reserva_Cohorte_Remanente.eq(1).all()


def test_calendar_alignment_handles_leap_year_and_reservoir_rejects_mixed_years():
    np.testing.assert_array_equal(
        reference_calendar_days(["2028-02-28", "2028-02-29", "2028-03-01", "2028-12-31"]),
        [59, 59.5, 60, 365],
    )
    weather = pd.DataFrame({"Fecha": ["2026-12-31", "2027-01-01"], "Prec": 0, "TMAX": 20, "TMIN": 10})
    with pytest.raises(ValueError, match="cada campaña"):
        simulate(weather)
