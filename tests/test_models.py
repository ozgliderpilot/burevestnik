from burevestnik.models import DaySummary, Forecast


def test_day_summary_constructs():
    d = DaySummary(
        label="Today",
        weekday="Sun",
        temp_max_c=21,
        temp_min_c=15,
        wind_kn_max=10,
        rain_mm_low=10.0,
        rain_mm_high=20.0,
        sun_hours=2.0,
    )
    assert d.temp_max_c == 21
    assert d.label == "Today"


def test_forecast_constructs():
    day = DaySummary(
        label="Today", weekday="Sun", temp_max_c=21, temp_min_c=15,
        wind_kn_max=10, rain_mm_low=10.0, rain_mm_high=20.0, sun_hours=2.0,
    )
    f = Forecast(
        today=day, tomorrow=day,
        peak_rain_mm=1.5, peak_rain_time="12:00",
        uv_index=2,
        temp_felt_max_c=18, temp_felt_min_c=10,
        wind_kn_low=2, wind_kn_high=7, gust_kn_max=22,
    )
    assert f.peak_rain_mm == 1.5
    assert f.temp_felt_max_c == 18
    assert f.temp_felt_min_c == 10
    assert f.wind_kn_low == 2
    assert f.wind_kn_high == 7
    assert f.gust_kn_max == 22


def test_forecast_has_uv_index():
    day = DaySummary(
        label="Today", weekday="Sun", temp_max_c=21, temp_min_c=15,
        wind_kn_max=10, rain_mm_low=10.0, rain_mm_high=20.0, sun_hours=2.0,
    )
    f = Forecast(
        today=day, tomorrow=day,
        peak_rain_mm=1.5, peak_rain_time="12:00",
        uv_index=4,
        temp_felt_max_c=18, temp_felt_min_c=10,
        wind_kn_low=2, wind_kn_high=7, gust_kn_max=22,
    )
    assert f.uv_index == 4


def test_dataclasses_are_frozen():
    d = DaySummary(
        label="Today", weekday="Sun", temp_max_c=21, temp_min_c=15,
        wind_kn_max=10, rain_mm_low=10.0, rain_mm_high=20.0, sun_hours=2.0,
    )
    import dataclasses
    try:
        d.temp_max_c = 99
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("DaySummary should be frozen")
