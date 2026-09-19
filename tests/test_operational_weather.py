import pandas as pd
from pathlib import Path

from predweem_twin.weather import (
    last_observed_weather_date, read_weather_file, forecast_mask, weather_source_label,
    operational_weather_window,
)


def test_calibration_weather_is_continuous_and_marks_three_provisional_days():
    data = Path(__file__).parents[1] / "data/calibration/san_pedro_2026_weather.csv"
    frame = read_weather_file(data)
    assert pd.to_datetime(frame.Fecha).tolist() == pd.date_range("2026-01-01", "2026-07-15").tolist()
    assert frame.TipoDato.value_counts().to_dict() == {"Observado": 193, "Provisional": 3}
    assert frame.loc[frame.TipoDato.eq("Provisional"), "Fecha"].tolist() == ["2026-06-09", "2026-06-10", "2026-06-11"]
    assert frame.loc[frame.TipoDato.eq("Observado"), "Fuente"].eq("SIGA_INTA_SAN_PEDRO_A872890").all()
    assert not forecast_mask(frame).any()


def test_operational_window_uses_last_non_forecast_date_and_seven_days():
    dates = pd.date_range("2026-03-29", periods=10, freq="D")
    weather = pd.DataFrame(
        {
            "Fecha": dates,
            "TMAX": 20.0,
            "TMIN": 10.0,
            "Prec": 0.0,
            "TipoDato": ["Observado", "Provisional", *(["Pronostico"] * 8)],
        }
    )

    cutoff = last_observed_weather_date(weather)
    window, metadata = operational_weather_window(weather, forecast_days=7)

    assert cutoff == pd.Timestamp("2026-03-30")
    assert metadata["as_of"] == pd.Timestamp("2026-03-30")
    assert metadata["forecast_days_available"] == 7
    assert metadata["forecast_end"] == pd.Timestamp("2026-04-06")
    assert metadata["complete"]
    assert window["Fecha"].max() == pd.Timestamp("2026-04-06")


def test_partial_file_without_forecast_is_reported_as_incomplete():
    weather = pd.DataFrame(
        {
            "Fecha": pd.date_range("2026-01-01", "2026-03-30", freq="D"),
            "TMAX": 20.0,
            "TMIN": 10.0,
            "Prec": 0.0,
        }
    )

    _, metadata = operational_weather_window(weather, forecast_days=7)

    assert metadata["as_of"] == pd.Timestamp("2026-03-30")
    assert metadata["forecast_days_available"] == 0
    assert not metadata["complete"]
