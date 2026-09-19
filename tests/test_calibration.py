from copy import deepcopy
from pathlib import Path
from hashlib import sha256

import numpy as np
import pandas as pd
import pytest

from predweem_twin.assimilation import assimilate_observations
from predweem_twin.calibration import (
    apply_site_calibration, calibrated_progress, calibration_intervals,
    fit_site_calibration, load_site_profile, model_fingerprint,
)
from predweem_twin.core import ModelParameters, PracticalANNModel, run_predweem
from predweem_twin.observations import prepare_observations
from predweem_twin.seasonal import load_seasonal_reference
from scripts.calibrate_site import read_site_counts


ROOT = Path(__file__).parents[1]
DATA = ROOT / "data/calibration"


def test_original_attachment_and_frozen_inputs_match_provenance():
    source = saved_profile()["source"]
    original = DATA / source["original_file"]
    assert sha256(original.read_bytes()).hexdigest() == source["uploaded_sha256"]
    excel = pd.read_excel(original)
    csv = pd.read_csv(DATA / source["observations_file"], parse_dates=["fecha"])
    pd.testing.assert_frame_equal(excel, csv, check_dtype=False)
    for stem in ("observations", "weather"):
        path = DATA / source[stem + "_file"]
        assert sha256(path.read_bytes()).hexdigest() == source[stem + "_sha256"]


def example_trajectory(year=2027):
    return pd.DataFrame({
        "Fecha": pd.date_range(f"{year}-01-01", periods=12),
        "EMERAC_NORMALIZADA": [0, 0, .02, .07, .07, .2, .4, .4, .6, .7, .7, .8],
        "EMERREL": [0, 0, 2, 5, 0, 13, 20, 0, 20, 10, 0, 10],
        "TT_DESDE_PICO": np.arange(12) * 10.,
    })


def saved_profile():
    return load_site_profile(DATA / "san_pedro_2026.json")


def apply(frame=None, **kwargs):
    arguments = {
        "site": "San Pedro", "as_of": "2027-01-08",
        "model_fingerprint": model_fingerprint(ROOT),
    }
    arguments.update(kwargs)
    return apply_site_calibration(
        example_trajectory() if frame is None else frame,
        saved_profile(), **arguments,
    )


def test_calibration_preserves_biophysical_gates_partial_tail_and_inputs():
    original = example_trajectory()
    before = original.copy(deep=True)
    result, audit = apply(original)
    assert audit["applied"]
    assert result.EMERAC_CALIBRADA.between(0, 1).all()
    assert result.EMERAC_CALIBRADA.is_monotonic_increasing
    assert result.EMERAC_CALIBRADA.iloc[-1] < 1  # partial season is not completed
    no_flux = before.EMERAC_NORMALIZADA.diff().fillna(0).eq(0)
    assert result.loc[no_flux, "EMERREL_CALIBRADA"].eq(0).all()
    pd.testing.assert_frame_equal(original, before)
    pd.testing.assert_series_equal(result.EMERREL, before.EMERREL)
    pd.testing.assert_series_equal(result.TT_DESDE_PICO, before.TT_DESDE_PICO)
    assert np.array_equal(calibrated_progress([0, 1], .8, 1.3), [0, 1])


@pytest.mark.parametrize("arguments", [
    {"enabled": False}, {"site": "Bordenave"},
    {"as_of": "2026-04-01"}, {"model_fingerprint": "other-model"},
])
def test_inapplicable_profile_returns_exact_original(arguments):
    original = example_trajectory()
    result, audit = apply(original, **arguments)
    assert not audit["applied"]
    np.testing.assert_array_equal(result.EMERAC_NORMALIZADA, original.EMERAC_NORMALIZADA)


def test_same_campaign_observations_are_not_reused_for_calibration_and_assimilation():
    frame = example_trajectory(2026)
    obs = pd.DataFrame({"Fecha": ["2026-01-04"], "Observado": [.1]})
    result, audit = apply(frame, as_of="2026-09-18", observations=obs)
    assert not audit["applied"]
    assert "reutilizar" in audit["reason"]
    original_twin, _ = assimilate_observations(frame, obs)
    actual_twin, _ = assimilate_observations(result, obs)
    np.testing.assert_array_equal(actual_twin.EMERAC_TWIN, original_twin.EMERAC_TWIN)


def test_new_season_observations_combine_with_persistent_profile():
    obs = pd.DataFrame({"Fecha": ["2027-01-06"], "Observado": [.25]})
    result, audit = apply(observations=obs)
    assert audit["applied"]
    twin, assimilation_audit = assimilate_observations(result, obs)
    assert len(assimilation_audit) == 1
    assert twin.EMERAC_TWIN.is_monotonic_increasing
    assert twin.EMERAC_TWIN.between(0, 1).all()
    assert twin.EMERAC_BASE_SIN_CALIBRAR.equals(result.EMERAC_BASE_SIN_CALIBRAR)


def test_invalid_profile_cannot_change_outputs():
    profile = deepcopy(saved_profile())
    profile["parameters"]["slope"] = float("nan")
    with pytest.raises(ValueError, match="finitos"):
        apply_site_calibration(example_trajectory(), profile, site="San Pedro", as_of="2027-01-08")


def test_known_transformation_can_be_learned_without_seasonal_total():
    dates = pd.date_range("2026-01-01", periods=100)
    progress = np.linspace(.01, .75, 100)
    frame = pd.DataFrame({"Fecha": dates, "EMERAC_NORMALIZADA": progress})
    sample = np.arange(2, 100, 7)
    truth = calibrated_progress(progress, offset=.8, slope=1.3)
    flows = np.diff(np.r_[0., truth[sample]]) * 1500
    obs = pd.DataFrame({"Fecha": dates[sample], "Flujo_observado_PLM2": flows})
    profile, comparison = fit_site_calibration(frame, obs, site="Example")
    assert profile["fit"]["rmse_calibrated_units"] < profile["fit"]["rmse_base_units"] * .5
    assert len(comparison) == len(obs) - 1
    assert profile["season_complete"] is False
    altered = obs.copy()
    altered.loc[0, "Flujo_observado_PLM2"] *= 100
    other, _ = fit_site_calibration(frame, altered, site="Example")
    assert other["parameters"] == profile["parameters"]  # unknown first interval excluded


@pytest.fixture(scope="module")
def real_data():
    weather = pd.read_csv(DATA / "san_pedro_2026_weather.csv")
    model = PracticalANNModel.from_directory(ROOT / "models")
    reference = load_seasonal_reference(
        ROOT / "models/modelo_clusters_k3.pkl", excluded_years=("2010", "2015"), include_patterns=("san pedro",),
    )
    trajectory = run_predweem(
        weather, model, ModelParameters(),
        normalization_as_of="2026-07-15", seasonal_reference=reference,
    )
    raw, prepared, metadata = read_site_counts(DATA / "san_pedro_2026_counts.csv")
    return trajectory, raw, prepared, metadata


def test_source_units_missing_replicates_and_irregular_intervals(real_data):
    trajectory, raw, prepared, metadata = real_data
    assert len(raw) == 12 and "n_repeticiones" not in metadata
    assert raw.columns.tolist() == ["fecha", "plantas"]
    assert raw.plantas.sum() == pytest.approx(3773.333333333333)
    _, intervals = calibration_intervals(trajectory, prepared)
    assert intervals.iloc[0]["Inicio_exclusivo"] == pd.Timestamp("2026-02-01")
    assert intervals.iloc[0]["Fecha"] == pd.Timestamp("2026-02-21")
    assert intervals.iloc[0]["Dias_intervalo"] == 20
    assert intervals.iloc[0]["Observado_Unidades"] == pytest.approx(2213.333333333333)
    assert intervals.loc[intervals.Fecha.eq("2026-03-01"), "Dias_intervalo"].iloc[0] == 8
    assert intervals.Dias_intervalo.min() == 8
    assert intervals.Dias_intervalo.max() == 20
    assert len(intervals) == 11
    assert intervals.EE_repeticiones_Unidades.isna().all()
    assert np.allclose(intervals.Sigma_ajuste_Unidades, 221.3333333333333)
    assert intervals.Observado_Unidades.sum() == pytest.approx(raw.iloc[:, -1].sum())


def test_calibration_keeps_san_pedro_termohydric_reservoir_and_local_reference(real_data):
    trajectory, _, _, _ = real_data
    result, audit = apply(trajectory, as_of="2026-07-15")
    assert audit["applied"]
    for column in ("EMERREL", "Factor_TermoHidrico", "Reserva_Cohorte", "TT_DESDE_PICO"):
        pd.testing.assert_series_equal(trajectory[column], result[column])
    blocked = trajectory.EMERAC_NORMALIZADA.diff().fillna(0).eq(0)
    assert result.loc[blocked, "EMERREL_CALIBRADA"].eq(0).all()
    saved = saved_profile()
    assert saved["model_parameters"]["cobertura_pct"] == ModelParameters().cobertura_pct
    assert saved["model_parameters"]["w_max"] == ModelParameters().w_max
    assert saved["model_parameters"]["ventana_termohidrica"] == 7
    assert saved["model_parameters"]["k_cohorte"] == ModelParameters().k_cohorte
    assert saved["seasonal_reference"]["include_patterns"] == ["san pedro"]
    assert saved["seasonal_reference"]["excluded_years"] == ["2010", "2015"]
    assert saved["seasonal_reference"]["n_campaigns"] == 1
    assert saved["source"]["density_units_confirmed"] is False
    assert saved["validation"]["base_model_uses_training_season"] is True


def test_fit_matches_persisted_profile_and_does_not_mutate_network(real_data):
    trajectory, _, prepared, _ = real_data
    fingerprint = model_fingerprint(ROOT)
    profile, comparison = fit_site_calibration(trajectory, prepared, site="San Pedro")
    saved = saved_profile()
    assert profile["parameters"] == saved["parameters"]
    assert profile["fit"]["rmse_base_units"] == pytest.approx(saved["fit"]["rmse_base_units"])
    assert profile["fit"]["rmse_calibrated_units"] == pytest.approx(saved["fit"]["rmse_calibrated_units"])
    assert model_fingerprint(ROOT) == fingerprint == saved["model_fingerprint"]


@pytest.mark.parametrize("fault", ["negative", "duplicate", "missing_weather", "nan"])
def test_invalid_training_data_are_rejected(real_data, fault):
    trajectory, _, prepared, _ = real_data
    trajectory, obs = trajectory.copy(), prepared.copy()
    if fault == "negative":
        obs.loc[3, "Flujo_observado_PLM2"] = -1
    elif fault == "duplicate":
        obs.loc[3, "Fecha"] = obs.loc[2, "Fecha"]
    elif fault == "missing_weather":
        trajectory = trajectory.drop(index=80)
    else:
        obs.loc[3, "Flujo_observado_PLM2"] = np.nan
    with pytest.raises(ValueError):
        fit_site_calibration(trajectory, obs, site="San Pedro")


def test_unconfirmed_count_units_are_not_imported_as_density():
    from predweem_twin.observations import read_observation_file
    with pytest.raises(ValueError, match="No se encontró"):
        read_observation_file(DATA / "san_pedro_2026_original.xlsx")
    raw, prepared, _ = read_site_counts(DATA / "san_pedro_2026_original.xlsx")
    np.testing.assert_allclose(raw.plantas, prepared.Flujo_observado_PLM2)
