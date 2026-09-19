"""Cierre inclusivo de la campaña en el gemelo."""
import pandas as pd
import pytest
from predweem_twin.weather import operational_weather_window

@pytest.mark.parametrize("cutoff,expected", [("2026-09-28", 3), ("2026-10-01", 0), ("2026-10-10", 0)])
def test_twin_horizon_stops_at_campaign_end(cutoff, expected):
    frame = pd.DataFrame({"Fecha": pd.date_range("2026-09-25", "2026-10-10")})
    window, meta = operational_weather_window(frame, as_of=cutoff)
    assert window.Fecha.max() == pd.Timestamp("2026-10-01")
    assert meta["forecast_days_expected"] == expected
    assert meta["forecast_days_available"] == expected
    assert meta["complete"]
