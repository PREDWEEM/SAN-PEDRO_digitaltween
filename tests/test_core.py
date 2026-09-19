from pathlib import Path
import importlib.util

import numpy as np
import pandas as pd
import pytest

from predweem_twin.core import (
    ModelParameters,
    PracticalANNModel,
    run_predweem,
)
from predweem_twin.state import thermal_window_dates
from sanpedro_calibracion_final import aplicar_agotamiento_cohorte, aplicar_interaccion_termohidrica


ROOT = Path(__file__).parents[1]

spec = importlib.util.spec_from_file_location(
    "san_pedro_original", ROOT / "tests/fixtures/san_pedro_original.py"
)
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


@pytest.mark.parametrize("coverage,wmax,kr", [(ModelParameters().cobertura_pct, ModelParameters().w_max, 0), (10, 10, 0), (60, 36, 1), (100, 5, 0)])
def test_extracted_core_matches_original_san_pedro(coverage, wmax, kr):
    weather = pd.read_csv(ROOT / "data/calibration/san_pedro_2026_weather.csv")
    model = PracticalANNModel.from_directory(ROOT / "models")
    original_model = original.PracticalANNModel(
        model.iw, model.bias_iw, model.lw, model.bias_out,
    )
    expected, first_peak, _, _ = original.simular_emergencia_local(
        weather, original_model, coverage, wmax, exponente_kr=kr,
    )
    result = run_predweem(
        weather, model, ModelParameters(cobertura_pct=coverage, w_max=wmax, exponente_kr=kr),
    )
    for column in (
        "EMERREL_RAW_ANN", "ET0", "W_superficial", "Hydric_Factor",
        "EMERREL", "EMERAC", "EMERAC_NORMALIZADA", "Factor_TermoHidrico",
        "Reserva_Cohorte", "Factor_Cohorte", "Fraccion_Liberada_Cohorte", "Tcrit_Efectiva", "TT_DESDE_PICO",
    ):
        if column in expected:
            np.testing.assert_allclose(result[column], expected[column], atol=1e-12, rtol=1e-12)
    expected_tt = np.zeros(len(expected))
    if first_peak is not None:
        daily_tt = expected.Tmedia.apply(lambda t: original.calculate_tt_scalar(t, 2., 20., 30.))
        expected_tt[first_peak:] = daily_tt.iloc[first_peak:].cumsum()
    np.testing.assert_allclose(result.TT_DESDE_PICO, expected_tt, atol=1e-12)
    assert result.Termoinhibida.equals(expected.Termoinhibida)
    assert result.Primer_Pico_Habilitado.equals(expected.Primer_Pico_Habilitado)


def test_reservoir_conserves_mass_and_does_not_use_future_pulses():
    frame = pd.DataFrame({"EMERREL": [0., .8, 0., .3, .9, .8]})
    full = aplicar_agotamiento_cohorte(frame, 1)
    prefix = aplicar_agotamiento_cohorte(frame.iloc[:4], 1)
    pd.testing.assert_frame_equal(full.iloc[:4], prefix)
    assert full.Reserva_Cohorte.is_monotonic_decreasing
    assert full.EMERREL.iloc[2] == 0
    assert full.EMERREL.sum() + full.Reserva_Cohorte.iloc[-1] - full.EMERREL.iloc[-1] == pytest.approx(1.)
    assert aplicar_agotamiento_cohorte(frame, None).EMERREL.eq(0).all()


def test_thermal_response_is_continuous_and_diagnostic_does_not_zero_flow():
    p = ModelParameters()
    frame = pd.DataFrame({
        "EMERREL": [.8] * 10, "Tmedia_aire": [p.umbral_termoinhibicion + 1] * 10,
        "Humedad_Relativa": [.8] * 10, "Prec_3d": [0.] * 10,
    })
    result = aplicar_interaccion_termohidrica(frame)
    assert result.Termoinhibida.all()
    assert result.Factor_TermoHidrico.between(0, .5, inclusive="neither").all()
    assert result.EMERREL.gt(0).all()
    assert not result.EMERREL.eq(frame.EMERREL).any()


def test_real_san_pedro_run_has_expected_invariants():
    weather = pd.read_csv(ROOT / "meteo_daily.csv")
    model = PracticalANNModel.from_directory(ROOT / "models")
    result = run_predweem(weather, model, ModelParameters())
    assert not result.empty
    assert result["Fecha"].is_monotonic_increasing
    assert result["EMERREL"].between(0, 1).all()
    assert result["EMERAC_NORMALIZADA"].between(0, 1).all()
    assert (result["W_superficial"] >= 0).all()
    assert (result["W_superficial"] <= ModelParameters().w_max + 1e-9).all()
    assert (result.loc[result["Julian_days"] <= 25, "EMERREL"] == 0).all()
    assert "Factor_TermoHidrico" in result
    assert "Reserva_Cohorte" in result


def test_weather_validation_rejects_inverted_temperatures():
    weather = pd.DataFrame(
        {"Fecha": ["2026-01-01"], "TMAX": [10], "TMIN": [15], "Prec": [0]}
    )
    model = PracticalANNModel.from_directory(ROOT / "models")
    try:
        run_predweem(weather, model, ModelParameters())
    except ValueError as error:
        assert "TMAX" in str(error)
    else:
        raise AssertionError("Se esperaba ValueError")


def test_run_uses_observed_daily_coverage_series():
    weather = pd.read_csv(ROOT / "meteo_daily.csv").head(5)
    weather_dates = pd.to_datetime(weather["Fecha"])
    coverage = pd.DataFrame(
        {
            "Fecha": [weather_dates.iloc[0], weather_dates.iloc[2]],
            "Cobertura_PCT": [20.0, 80.0],
        }
    )
    model = PracticalANNModel.from_directory(ROOT / "models")

    result = run_predweem(
        weather,
        model,
        ModelParameters(cobertura_pct=40.0),
        coverage_series=coverage,
    )

    assert np.allclose(
        result["Cobertura_Rastrojo"], [20.0, 50.0, 80.0, 80.0, 80.0]
    )
    assert result["Cobertura_Modo"].eq("serie observada interpolada").all()
    assert result["Cobertura_Observada"].tolist() == [True, False, True, False, False]


def test_thermal_window_dates_detects_600_and_800_degree_days():
    trajectory = pd.DataFrame(
        {
            "Fecha": pd.date_range("2026-04-01", periods=5, freq="D"),
            "TT_DESDE_PICO": [550.0, 600.0, 710.0, 800.0, 850.0],
        }
    )

    start, end = thermal_window_dates(trajectory)

    assert start == pd.Timestamp("2026-04-02")
    assert end == pd.Timestamp("2026-04-04")
