from pathlib import Path
import pickle

import numpy as np
import pandas as pd
import pytest

from predweem_twin.core import ModelParameters, PracticalANNModel, run_predweem
from predweem_twin.seasonal import load_seasonal_reference, reference_calendar_days
from scripts.build_seasonal_reference import build_reference

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "data/reference/san_pedro_2023_2026.json"


def simulate(weather, cutoff="2026-03-30", reference=None):
    return run_predweem(
        weather, PracticalANNModel.from_directory(ROOT / "models"), ModelParameters(),
        normalization_as_of=cutoff, seasonal_reference=reference,
    )


def test_complete_campaigns_preserve_their_sources_and_equal_weight():
    reference = load_seasonal_reference(SOURCE)
    assert reference.N_Campanas.eq(4).all()
    assert reference.Campanas.eq("2023, 2024, 2025, 2026").all()
    assert reference.Campanas_Sin_Cero_Inicial.eq("2023, 2024").all()
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
    # 2023 y 2024 también conservan el acumulado y la masa de cada intervalo.
    for year, first in ((2023, "2023-04-14"), (2024, "2024-03-16")):
        data = pd.read_csv(ROOT / f"data/reference/san_pedro_{year}_counts.csv", parse_dates=["fecha"])
        observed = reference.set_index("Julian_days").loc[data.fecha.dt.dayofyear, f"Progreso_{year}"]
        np.testing.assert_allclose(observed, data.plantas.cumsum() / data.plantas.sum())
        np.testing.assert_allclose(np.diff(observed), data.plantas.iloc[1:] / data.plantas.sum(), atol=1e-14)
        start = pd.Timestamp(first).dayofyear
        # Sin cero inicial: vacío antes del primer conteo, que entra con su masa.
        assert reference[f"Progreso_{year}"].iloc[:start - 1].isna().all()
        assert reference[f"Progreso_{year}"].iloc[start - 1] == pytest.approx(data.plantas.iloc[0] / data.plantas.sum())
        assert reference[f"Progreso_{year}"].iloc[data.fecha.iloc[-1].dayofyear - 1:].eq(1).all()
    columns = [f"Progreso_{year}" for year in (2023, 2024, 2025, 2026)]
    allfour = reference.iloc[pd.Timestamp("2023-04-14").dayofyear - 1:]
    assert allfour.N_Campanas_Dia.eq(4).all()
    np.testing.assert_allclose(allfour.Progreso_Mediano, allfour[columns].median(axis=1))
    np.testing.assert_allclose(allfour.Progreso_Min, allfour[columns].min(axis=1))
    np.testing.assert_allclose(allfour.Progreso_Max, allfour[columns].max(axis=1))
    # Antes del 01/02 sólo 2024 (desde el 16/03) y 2025 aportan; no se rellena con ceros.
    january = reference.iloc[:31]
    assert january.N_Campanas_Dia.eq(1).all()
    np.testing.assert_allclose(january.Progreso_Mediano, january.Progreso_2025)
    assert reference.loc[reference.Julian_days.eq(70), "N_Campanas_Dia"].iloc[0] == 2


def test_reference_excludes_campaigns_closed_after_cutoff():
    early = load_seasonal_reference(SOURCE, as_of="2026-04-05")
    assert early.N_Campanas.eq(3).all()
    assert early.Campanas.eq("2023, 2024, 2025").all()
    assert "Progreso_2026" not in early
    assert "no disponibles al corte: San Pedro 2026" in early.Campanas_Excluidas.iloc[0]
    assert load_seasonal_reference(SOURCE, as_of="2026-07-15").N_Campanas.eq(4).all()
    # Cada campaña recién existe desde su último conteo.
    assert load_seasonal_reference(SOURCE, as_of="2023-10-01").Campanas.eq("2023").all()
    assert load_seasonal_reference(SOURCE, as_of="2024-10-16").Campanas.eq("2023").all()
    assert load_seasonal_reference(SOURCE, as_of="2024-10-17").Campanas.eq("2023, 2024").all()
    with pytest.raises(ValueError, match="No hay campañas"):
        load_seasonal_reference(SOURCE, as_of="2023-09-30")


def test_reference_rebuild_is_reproducible_and_corruption_is_rejected(tmp_path):
    build_reference(tmp_path)
    for name in ("san_pedro_2023_2026.json", "san_pedro_2023_2026_curves.csv"):
        assert (tmp_path / name).read_bytes() == (SOURCE.parent / name).read_bytes()
    curves = tmp_path / "san_pedro_2023_2026_curves.csv"
    curves.write_text(curves.read_text() + "\n")
    with pytest.raises(ValueError, match="procedencia"):
        load_seasonal_reference(tmp_path / SOURCE.name)


def test_2023_2024_provenance_documents_units_origin_and_missing_initial_zero():
    import json
    from hashlib import sha256
    manifest = json.loads(SOURCE.read_text(encoding="utf-8"))
    source = json.loads((ROOT / manifest["provenance_2023_2024"]["file"]).read_text(encoding="utf-8"))
    assert sha256((ROOT / manifest["provenance_2023_2024"]["file"]).read_bytes()).hexdigest() \
        == manifest["provenance_2023_2024"]["sha256"]
    assert source["site"] == "San Pedro" and source["units"].startswith("plantas/m²")
    assert "sin cero inicial" in " ".join(
        item["limitation"].lower() for item in manifest["campaigns"] if item["year"] in (2023, 2024)
    )
    for item in manifest["campaigns"]:
        if item["year"] not in (2023, 2024):
            continue
        assert item["initial_zero"] is False and item["density_units"] == "plantas/m²"
        for key in ("source", "original_file"):
            data = (ROOT / item[key]).read_bytes()
            assert sha256(data).hexdigest() == item["source_sha256" if key == "source" else "original_sha256"]
        # El CSV conserva exactamente los conteos del Excel recibido.
        original = pd.read_excel(ROOT / item["original_file"])
        counts = pd.read_csv(ROOT / item["source"], parse_dates=["fecha"])
        np.testing.assert_array_equal(original["plantas"].to_numpy(float), counts["plantas"].to_numpy(float))
        assert (pd.to_datetime(original["fecha"]).to_numpy() == counts["fecha"].to_numpy()).all()


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


def test_pool_2027_is_exclusively_the_four_san_pedro_campaigns(tmp_path):
    import json
    from hashlib import sha256
    reference = load_seasonal_reference(SOURCE, as_of="2027-05-05")
    manifest = build_reference(tmp_path)
    manifest["campaigns"].append({
        "year": 2022, "complete": True, "available_from": "2023-01-01",
        "source": "otra_localidad.csv", "site": "Otra localidad",
    })
    curves_path = tmp_path / manifest["curves_file"]
    curves = pd.read_csv(curves_path)
    extra = pd.DataFrame({"Campana": 2022, "Julian_days": np.arange(1, 366), "Progreso": 1.})
    pd.concat([curves, extra], ignore_index=True).to_csv(curves_path, index=False)
    manifest["curves_sha256"] = sha256(curves_path.read_bytes()).hexdigest()
    (tmp_path / SOURCE.name).write_text(json.dumps(manifest))
    actual = load_seasonal_reference(tmp_path / SOURCE.name, as_of="2027-05-05")
    assert actual.Campanas_Anos.eq("2023, 2024, 2025, 2026").all()
    assert actual.N_Campanas.eq(4).all()
    assert "Progreso_2022" not in actual
    np.testing.assert_allclose(actual.Progreso_Mediano, reference.Progreso_Mediano)
    assert ("excepto San Pedro 2023, San Pedro 2024, San Pedro 2025, San Pedro 2026"
            in actual.Campanas_Excluidas.iloc[0])


@pytest.mark.parametrize("fault", ["site", "curve", "source", "source_2024", "duplicate"])
def test_local_pool_rejects_wrong_site_source_or_duplicate_campaign(tmp_path, fault):
    import json
    manifest = build_reference(tmp_path)
    by_year = {item["year"]: item for item in manifest["campaigns"]}
    if fault == "site":
        manifest["site"] = "Balcarce"
    elif fault == "curve":
        by_year[2025]["source_curve"] = "emrel balcarce 2025.xlsx"
    elif fault == "source":
        by_year[2026]["source"] = "data/calibration/azul_2026_counts.csv"
    elif fault == "source_2024":
        by_year[2024]["source"] = "data/reference/azul_2024_counts.csv"
    else:
        manifest["campaigns"].append(by_year[2023].copy())
    (tmp_path / SOURCE.name).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="San Pedro"):
        load_seasonal_reference(tmp_path / SOURCE.name, as_of="2027-05-05")


def test_historical_flow_is_mean_of_campaigns_with_data_on_both_days():
    from predweem_twin.flows import annual_historical_reference
    reference = load_seasonal_reference(SOURCE, as_of="2027-05-05")
    annual = annual_historical_reference(reference, "2027-05-05")
    campaigns = [f"Progreso_{year}" for year in (2023, 2024, 2025, 2026)]
    daily = annual[campaigns].diff()
    np.testing.assert_allclose(annual.Flujo_Diario.iloc[1:], daily.mean(axis=1, skipna=True).clip(lower=0).iloc[1:],
                               atol=1e-14)
    # Un conteo inicial no nulo no crea flujo previo ni un salto en el pool:
    # el día de entrada de 2023 el flujo sólo depende de las otras tres campañas.
    entry = annual.index[annual.Fecha.eq("2027-04-14")][0]
    others = daily.loc[entry, ["Progreso_2024", "Progreso_2025", "Progreso_2026"]].mean()
    assert np.isnan(daily.loc[entry, "Progreso_2023"])
    assert annual.Flujo_Diario.loc[entry] == pytest.approx(max(others, 0))
    # Con las dos campañas 2025–2026 equivale a la derivada de su mediana.
    pair = reference[["Julian_days", "Progreso_2025", "Progreso_2026"]].copy()
    pair["Progreso_Mediano"] = pair[["Progreso_2025", "Progreso_2026"]].median(axis=1)
    pair["Campanas_Anos"] = "2025, 2026"
    two = annual_historical_reference(pair, "2027-05-05")
    paired = two.loc[two.Fecha.ge("2027-02-01")]
    np.testing.assert_allclose(paired.Flujo_Diario,
                               (paired.Progreso_2025.diff().fillna(0) + paired.Progreso_2026.diff().fillna(0)).div(2),
                               atol=1e-14)
    assert two.Flujo_Diario.sum() == pytest.approx(1)
    np.testing.assert_allclose(two.Flujo_Diario.cumsum(), two.Progreso_Mediano)
