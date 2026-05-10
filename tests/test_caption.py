from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from burevestnik.caption import render
from burevestnik.models import DaySummary, Forecast

_SOURCE_URL = "https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810"


_DEFAULT_TOMORROW = DaySummary(
    label="Tomorrow", weekday="Mon",
    temp_max_c=17, temp_min_c=13,
    wind_kn_max=12,
    rain_mm_low=0.0, rain_mm_high=2.0,
    sun_hours=6.0,
)


def _make_forecast(
    peak_pct: int = 88,
    peak_time: str = "12:00",
    tomorrow: DaySummary | None = _DEFAULT_TOMORROW,
    uv_index: int = 2,
) -> Forecast:
    today = DaySummary(
        label="Today", weekday="Sun",
        temp_max_c=21, temp_min_c=15,
        wind_kn_max=10,
        rain_mm_low=10.0, rain_mm_high=20.0,
        sun_hours=2.0,
    )
    return Forecast(today=today, tomorrow=tomorrow,
                    peak_rain_pct=peak_pct, peak_rain_time=peak_time,
                    uv_index=uv_index)


def test_render_full_template():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now, _SOURCE_URL)

    # Header line
    assert "<b>Melbourne CBD</b>" in out
    assert "Sunday" in out
    assert "3 May" in out

    # Today temps
    assert "<b>21°</b>" in out
    assert "Low 15°" in out

    # Rain line
    assert "10–20mm" in out                 # en-dash
    assert "<b>88%</b>" in out
    assert "at 12:00" in out

    # Wind (knots)
    assert "Wind up to 10kn" in out

    # Sun line — sunrise/sunset just need to be HH:MM format
    assert "Sun 2h" in out
    import re
    assert re.search(r"🌅 \d{2}:\d{2}", out)
    assert re.search(r"🌇 \d{2}:\d{2}", out)

    # Tomorrow line
    assert "<i>Tomorrow:</i> 17°/13°" in out
    assert "0–2mm" in out
    assert "wind 12kn" in out

    # Updated stamp + meteoblue attribution link (per their T&Cs §9.05)
    assert "Updated 14:32" in out
    assert "AEST" in out  # May is standard time in Melbourne
    assert f'<a href="{_SOURCE_URL}">meteoblue</a>' in out


def test_caption_under_1024_chars():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now, _SOURCE_URL)
    assert len(out) <= 1024, f"caption is {len(out)} chars (Telegram max 1024)"


def test_collapses_equal_rain_range():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(peak_pct=50, peak_time="12:00")
    # Replace today with rain_mm_low == rain_mm_high
    today = DaySummary(
        label="Today", weekday="Sun",
        temp_max_c=21, temp_min_c=15, wind_kn_max=10,
        rain_mm_low=5.0, rain_mm_high=5.0, sun_hours=2.0,
    )
    f = Forecast(today=today, tomorrow=f.tomorrow,
                 peak_rain_pct=f.peak_rain_pct, peak_rain_time=f.peak_rain_time,
                 uv_index=f.uv_index)
    out = render(f, now, _SOURCE_URL)
    assert "5mm" in out
    assert "5–5mm" not in out
    assert "5-5mm" not in out


def test_drops_rain_line_when_zero_peak():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(peak_pct=0, peak_time="")
    out = render(f, now, _SOURCE_URL)
    assert "☔" not in out
    assert "Peak" not in out
    # Other lines still present
    assert "🌡" in out
    assert "💨" in out


def test_drops_sun_line_when_astral_unavailable():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast()
    with patch("burevestnik.caption._sunrise_sunset", return_value=(None, None)):
        out = render(f, now, _SOURCE_URL)
    assert "☀" not in out
    assert "🌅" not in out
    assert "🌇" not in out
    # Wind/temp/tomorrow still present
    assert "💨" in out
    assert "Tomorrow:" in out


def test_render_tomorrow_mode_header_contains_tomorrow_prefix_and_shifted_date():
    # Run time: Sun 10 May 2026 18:00 → forecast date is Mon 11 May.
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(tomorrow=None)
    out = render(f, now, _SOURCE_URL, for_tomorrow=True)

    # Header: "🌦 <b>Melbourne CBD</b> · Tomorrow, Monday 11 May"
    assert "<b>Melbourne CBD</b>" in out
    assert "Tomorrow, Monday" in out
    assert "11 May" in out
    # Today-mode header pattern must NOT appear (no plain "Sunday, 10 May").
    assert "Sunday, 10 May" not in out


def test_render_tomorrow_mode_omits_preview_line():
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(tomorrow=None)
    out = render(f, now, _SOURCE_URL, for_tomorrow=True)
    assert "<i>Tomorrow:</i>" not in out


def test_render_tomorrow_mode_keeps_run_time_in_updated_line():
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(tomorrow=None)
    out = render(f, now, _SOURCE_URL, for_tomorrow=True)
    # "Updated 18:00 AEST" — the actual run time, not the forecast date.
    assert "Updated 18:00" in out


def test_render_tomorrow_mode_uses_shifted_date_for_sun_lookup():
    # The sunrise/sunset lookup must be for the forecast date (11 May), not
    # the run date (10 May). Spy on _sunrise_sunset to capture its argument.
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(tomorrow=None)

    captured: dict = {}

    def spy(now_arg):
        captured["date"] = now_arg.date()
        return ("06:00", "17:00")

    with patch("burevestnik.caption._sunrise_sunset", side_effect=spy):
        render(f, now, _SOURCE_URL, for_tomorrow=True)

    from datetime import date
    assert captured["date"] == date(2026, 5, 11)
