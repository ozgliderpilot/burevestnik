from datetime import datetime
from zoneinfo import ZoneInfo
from burevestnik.main import should_forecast_tomorrow

_TZ = ZoneInfo("Australia/Melbourne")


def test_should_forecast_tomorrow_false_at_15_59():
    assert should_forecast_tomorrow(datetime(2026, 5, 10, 15, 59, tzinfo=_TZ)) is False


def test_should_forecast_tomorrow_true_at_16_00_exactly():
    # 16:00:00 is "past 4 PM" colloquially — cutoff fires at the top of the hour.
    assert should_forecast_tomorrow(datetime(2026, 5, 10, 16, 0, tzinfo=_TZ)) is True


def test_should_forecast_tomorrow_true_late_evening():
    assert should_forecast_tomorrow(datetime(2026, 5, 10, 23, 0, tzinfo=_TZ)) is True


def test_should_forecast_tomorrow_false_at_midnight():
    assert should_forecast_tomorrow(datetime(2026, 5, 11, 0, 0, tzinfo=_TZ)) is False
