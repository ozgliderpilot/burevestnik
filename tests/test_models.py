from datetime import date, datetime
from zoneinfo import ZoneInfo

from burevestnik.models import (
    DaySummary,
    Forecast,
    ForecastDay,
    ForecastDayKind,
    forecast_day,
)

_TZ = ZoneInfo("Australia/Melbourne")
_TODAY = ForecastDay.today(date(2026, 5, 3))


def _day_summary() -> DaySummary:
    return DaySummary(
        label="Today",
        weekday="Sun",
        temp_max_c=21,
        temp_min_c=15,
        wind_kn_max=10,
        rain_mm_low=10.0,
        rain_mm_high=20.0,
        sun_hours=2.0,
    )


def test_forecast_day_today_before_cutoff():
    day = forecast_day(datetime(2026, 5, 10, 15, 59, tzinfo=_TZ))
    assert day == ForecastDay.today(date(2026, 5, 10))
    assert day.page_index == 1


def test_forecast_day_tomorrow_at_cutoff():
    # 16:00:00 is "past 4 PM" colloquially — cutoff fires at the top of the hour.
    day = forecast_day(datetime(2026, 5, 10, 16, 0, tzinfo=_TZ))
    assert day == ForecastDay.tomorrow(date(2026, 5, 11))
    assert day.page_index == 2


def test_forecast_day_tomorrow_late_evening():
    day = forecast_day(datetime(2026, 5, 10, 23, 0, tzinfo=_TZ))
    assert day.kind is ForecastDayKind.TOMORROW
    assert day.date == date(2026, 5, 11)


def test_forecast_day_today_at_midnight():
    day = forecast_day(datetime(2026, 5, 11, 0, 0, tzinfo=_TZ))
    assert day == ForecastDay.today(date(2026, 5, 11))


def test_day_summary_constructs():
    d = _day_summary()
    assert d.temp_max_c == 21
    assert d.label == "Today"


def test_forecast_constructs():
    summary = _day_summary()
    f = Forecast(
        day=_TODAY,
        primary=summary, next_day_preview=summary,
        peak_rain_mm=1.5, peak_rain_time="12:00",
        uv_index=2,
        temp_felt_max_c=18, temp_felt_min_c=10,
        wind_kn_low=2, wind_kn_high=7, gust_kn_max=22,
        sunrise="07:03", sunset="17:30",
    )
    assert f.day == _TODAY
    assert f.peak_rain_mm == 1.5
    assert f.temp_felt_max_c == 18
    assert f.temp_felt_min_c == 10
    assert f.wind_kn_low == 2
    assert f.wind_kn_high == 7
    assert f.gust_kn_max == 22


def test_forecast_has_uv_index():
    summary = _day_summary()
    f = Forecast(
        day=_TODAY,
        primary=summary, next_day_preview=summary,
        peak_rain_mm=1.5, peak_rain_time="12:00",
        uv_index=4,
        temp_felt_max_c=18, temp_felt_min_c=10,
        wind_kn_low=2, wind_kn_high=7, gust_kn_max=22,
        sunrise="07:03", sunset="17:30",
    )
    assert f.uv_index == 4


def test_dataclasses_are_frozen():
    d = _day_summary()
    import dataclasses
    try:
        d.temp_max_c = 99
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("DaySummary should be frozen")
