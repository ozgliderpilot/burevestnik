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
    peak_mm: float = 1.5,
    peak_time: str = "12:00",
    tomorrow: DaySummary | None = _DEFAULT_TOMORROW,
    uv_index: int = 2,
    rain_mm_low: float = 10.0,
    rain_mm_high: float = 20.0,
    temp_felt_max_c: int = 18,
    temp_felt_min_c: int = 10,
) -> Forecast:
    today = DaySummary(
        label="Today", weekday="Sun",
        temp_max_c=21, temp_min_c=15,
        wind_kn_max=10,
        rain_mm_low=rain_mm_low, rain_mm_high=rain_mm_high,
        sun_hours=2.0,
    )
    return Forecast(
        today=today, tomorrow=tomorrow,
        peak_rain_mm=peak_mm, peak_rain_time=peak_time,
        uv_index=uv_index,
        temp_felt_max_c=temp_felt_max_c, temp_felt_min_c=temp_felt_min_c,
    )


def test_render_full_template():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now, _SOURCE_URL)

    # Header line
    assert "<b>Melbourne CBD</b>" in out
    assert "Sunday" in out
    assert "3 May" in out

    # Felt-temp headline (no <b>, hand+thermometer icon)
    assert "🤚🌡 High 18° / Low 10°" in out

    # Rain line — peak mm, bold value
    assert "10–20mm" in out                 # en-dash
    assert "<b>1.5mm</b>" in out
    assert "at 12:00" in out

    # Wind (knots)
    assert "Wind up to 10kn" in out

    # Sun line — sunrise/sunset just need to be HH:MM format
    assert "Sun 2h" in out
    import re
    assert re.search(r"🌅 \d{2}:\d{2}", out)
    assert re.search(r"🌇 \d{2}:\d{2}", out)

    # Tomorrow preview line still uses ACTUAL temps (no felt data for next day).
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
    f = _make_forecast(rain_mm_low=5.0, rain_mm_high=5.0, peak_mm=0.5, peak_time="12:00")
    out = render(f, now, _SOURCE_URL)
    assert "5mm" in out
    assert "5–5mm" not in out
    assert "5-5mm" not in out


def test_renders_no_rain_when_daily_range_zero():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(rain_mm_low=0.0, rain_mm_high=0.0, peak_mm=0.0, peak_time="")
    out = render(f, now, _SOURCE_URL)
    assert "☔ No rain" in out
    assert "Peak" not in out
    # Other lines still present
    assert "🤚🌡" in out
    assert "💨" in out


def test_omits_peak_tail_when_peak_mm_zero_but_range_nonzero():
    # Mirrors the current fixture's situation: 47% probability but every
    # hourly mm cell is empty/0, while the daily range is 0–2mm.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(rain_mm_low=0.0, rain_mm_high=2.0, peak_mm=0.0, peak_time="")
    out = render(f, now, _SOURCE_URL)
    assert "☔ Rain 0–2mm" in out
    assert "Peak" not in out


def test_render_peak_mm_formats_one_decimal():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(peak_mm=1.5, peak_time="14:00"), now, _SOURCE_URL)
    assert "Peak <b>1.5mm</b> at 14:00" in out


def test_render_peak_mm_strips_trailing_zero():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(peak_mm=12.0, peak_time="14:00"), now, _SOURCE_URL)
    assert "Peak <b>12mm</b> at 14:00" in out
    assert "12.0mm" not in out


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


import pytest


@pytest.mark.parametrize(
    "uv,expected_emoji,expected_label",
    [
        (0,  "🟢", "Low"),
        (1,  "🟢", "Low"),
        (2,  "🟢", "Low"),
        (3,  "🟡", "Moderate"),
        (4,  "🟡", "Moderate"),
        (5,  "🟡", "Moderate"),
        (6,  "🟠", "High"),
        (7,  "🟠", "High"),
        (8,  "🔴", "Very High"),
        (9,  "🔴", "Very High"),
        (10, "🔴", "Very High"),
        (11, "🟣", "Extreme"),
        (15, "🟣", "Extreme"),
    ],
)
def test_uv_band_maps_to_emoji_and_label(uv, expected_emoji, expected_label):
    from burevestnik.caption import _uv_band
    emoji, label = _uv_band(uv)
    assert emoji == expected_emoji
    assert label == expected_label


def test_render_includes_uv_line_today_mode():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(uv_index=2), now, _SOURCE_URL)
    assert "UV index: 🟢 2 (Low)" in out


def test_render_includes_uv_line_tomorrow_mode():
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(tomorrow=None, uv_index=7)
    out = render(f, now, _SOURCE_URL, for_tomorrow=True)
    assert "UV index: 🟠 7 (High)" in out


def test_render_uv_line_appears_after_sun_line():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(uv_index=4), now, _SOURCE_URL)
    lines = out.splitlines()
    sun_idx = next(i for i, line in enumerate(lines) if "Sun 2h" in line)
    uv_idx = next(i for i, line in enumerate(lines) if "UV index:" in line)
    assert uv_idx == sun_idx + 1, (
        f"UV line should immediately follow sun line; "
        f"got sun at {sun_idx}, UV at {uv_idx}"
    )


def test_render_uv_line_appears_after_wind_when_sun_unavailable():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(uv_index=4)
    with patch("burevestnik.caption._sunrise_sunset", return_value=(None, None)):
        out = render(f, now, _SOURCE_URL)
    assert "☀" not in out  # sun line dropped
    lines = out.splitlines()
    wind_idx = next(i for i, line in enumerate(lines) if "Wind up to 10kn" in line)
    uv_idx = next(i for i, line in enumerate(lines) if "UV index:" in line)
    assert uv_idx == wind_idx + 1, (
        f"UV line should immediately follow wind line when sun is dropped; "
        f"got wind at {wind_idx}, UV at {uv_idx}"
    )


def test_render_tomorrow_preview_line_does_not_include_uv():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(uv_index=4), now, _SOURCE_URL)
    # The "<i>Tomorrow:</i> ..." line previews next-day stats but must NOT
    # carry a UV value (meteoblue exposes no per-day UV in any day tab).
    tomorrow_line = next(line for line in out.splitlines() if line.startswith("<i>Tomorrow:</i>"))
    assert "UV" not in tomorrow_line


def test_render_uv_line_present_at_uv_zero():
    # UV 0 still renders — the layout is unconditional.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(uv_index=0), now, _SOURCE_URL)
    assert "UV index: 🟢 0 (Low)" in out
