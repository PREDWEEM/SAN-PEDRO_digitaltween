"""Integración del actualizador original de San Pedro, sin consultas de red."""
from datetime import date, timedelta
import json

import pandas as pd
import pytest

import actualizar_meteo_san_pedro as base
import actualizar_meteo_san_pedro_robusto as updater


def block(start, end, kind):
    df = pd.DataFrame({"Fecha": pd.date_range(start, end).strftime("%Y-%m-%d")})
    df["TMAX"], df["TMIN"], df["TMEDIA"], df["Prec"] = 20., 10., 15., 1.
    df["TipoDato"] = kind
    df["Fuente"] = {"Observado": "SIGA_INTA_SAN_PEDRO_A872890", "Provisional": "ECMWF_IFS_HISTORICO", "Pronostico": "ECMWF_IFS_ENS_025"}[kind]
    if kind == "Pronostico":
        for column in ("TMAX", "TMIN", "TMEDIA", "Prec"):
            df[column + "_P50"] = df[column]
        df["N_miembros"] = 51
    return updater.columnas(df)


@pytest.mark.parametrize("today", [date(2026, 9, 19), date(2026, 9, 29), date(2026, 10, 1), date(2026, 10, 8)])
def test_pipeline_fills_interior_gaps_and_stops_at_campaign_end(monkeypatch, tmp_path, today):
    yesterday = min(today - timedelta(days=1), base.CAMPANIA_END)
    observed = block(base.CAMPANIA_START, yesterday, "Observado")
    observed = observed[observed.Fecha != "2026-06-10"].copy()
    observed.loc[observed.Fecha.eq("2026-06-09"), "Prec"] = float("nan")
    forecast = block(today, min(today + timedelta(days=6), base.CAMPANIA_END), "Pronostico")
    monkeypatch.setattr(base, "hoy_argentina", lambda: today)
    monkeypatch.setattr(base, "ARCHIVO_MAESTRO_DEFAULT", tmp_path / "meteo.csv")
    monkeypatch.setattr(base, "ARCHIVO_SIGA_CACHE", tmp_path / "siga.csv")
    monkeypatch.setattr(base, "ARCHIVO_ESTADO", tmp_path / "state.json")
    def get_siga(start, end):
        assert start == base.CAMPANIA_START
        assert end == yesterday
        return observed, "test"
    monkeypatch.setattr(base, "obtener_siga_dataframe", get_siga)
    requests = []
    def get_bridge(start, end):
        requests.append((start, end))
        return block(start, end, "Provisional")
    monkeypatch.setattr(updater, "cargar_provisional", get_bridge)
    monkeypatch.setattr(base, "consultar_ecmwf_ens", lambda: {})
    monkeypatch.setattr(updater, "procesar_ens", lambda _: forecast)
    monkeypatch.setattr(base, "DIRECTORIO_PRONOSTICOS", tmp_path / "forecasts")
    result = updater.ejecutar()
    final = min(today + timedelta(days=6), base.CAMPANIA_END)
    assert result.Fecha.max() == final.isoformat()
    assert len(result) == (final - base.CAMPANIA_START).days + 1
    assert requests == [(date(2026, 6, 9), date(2026, 6, 10))]
    assert result.TipoDato.eq("Provisional").sum() == 2
    assert result.TipoDato.eq("Pronostico").sum() == len(forecast)
    assert (result.loc[result.TipoDato.eq("Provisional"), "Prec"] == 1.).all()
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["fecha_fin_campania"] == "2026-10-01"
    assert state["huecos_finales"] == []
    # Newly published valid station observations replace the bridge.
    observed.loc[observed.Fecha.eq("2026-06-09"), "Prec"] = 2.
    observed = pd.concat([observed, block("2026-06-10", "2026-06-10", "Observado")], ignore_index=True)
    requests.clear()
    updated = updater.ejecutar()
    assert not requests
    assert not updated.TipoDato.eq("Provisional").any()
    assert updated.loc[updated.Fecha.eq("2026-06-09"), "Prec"].iloc[0] == 2.


def test_closed_campaign_does_not_query_ensemble(monkeypatch):
    monkeypatch.setattr(base, "hoy_argentina", lambda: date(2026, 10, 2))
    def unexpected():
        raise AssertionError("No debe consultar pronóstico tras el cierre")
    monkeypatch.setattr(base, "consultar_ecmwf_ens", unexpected)
    assert updater.cargar_ens().empty


def test_invalid_weather_does_not_replace_operational_file(monkeypatch, tmp_path):
    today = date(2026, 9, 19)
    path = tmp_path / "meteo.csv"
    path.write_text("archivo anterior íntegro\n")
    monkeypatch.setattr(base, "hoy_argentina", lambda: today)
    monkeypatch.setattr(base, "ARCHIVO_MAESTRO_DEFAULT", path)
    monkeypatch.setattr(base, "ARCHIVO_SIGA_CACHE", tmp_path / "siga.csv")
    monkeypatch.setattr(base, "obtener_siga_dataframe", lambda *args: (block("2026-01-01", "2026-09-18", "Observado"), "test"))
    forecast = block(today, today + timedelta(days=6), "Pronostico")
    forecast.loc[0, "Prec"] = float("nan")
    monkeypatch.setattr(updater, "cargar_ens", lambda: forecast)
    with pytest.raises(ValueError, match="nulos"):
        updater.ejecutar()
    assert path.read_text() == "archivo anterior íntegro\n"
