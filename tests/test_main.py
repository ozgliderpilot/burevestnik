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


from burevestnik.main import should_post_outlook

# Fixture confirms 2026-05-05 is a Tuesday → 05-04 Mon, 05-07 Thu, 05-05 Tue.


def test_should_post_outlook_true_monday_morning():
    assert should_post_outlook(datetime(2026, 5, 4, 4, 17, tzinfo=_TZ)) is True


def test_should_post_outlook_true_thursday_morning():
    assert should_post_outlook(datetime(2026, 5, 7, 4, 17, tzinfo=_TZ)) is True


def test_should_post_outlook_false_monday_after_cutoff():
    assert should_post_outlook(datetime(2026, 5, 4, 16, 0, tzinfo=_TZ)) is False


def test_should_post_outlook_false_thursday_after_cutoff():
    assert should_post_outlook(datetime(2026, 5, 7, 16, 0, tzinfo=_TZ)) is False


def test_should_post_outlook_false_other_weekday_morning():
    assert should_post_outlook(datetime(2026, 5, 5, 4, 17, tzinfo=_TZ)) is False  # Tue
