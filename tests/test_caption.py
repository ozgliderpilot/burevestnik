from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from burevestnik.caption import render
from burevestnik.models import DaySummary, Forecast, ForecastDay

_SOURCE_URL = "https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810"
_TOMORROW_DAY = ForecastDay.tomorrow(date(2026, 5, 11))


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
    next_day_preview: DaySummary | None = _DEFAULT_TOMORROW,
    uv_index: int = 2,
    rain_mm_low: float = 10.0,
    rain_mm_high: float = 20.0,
    temp_felt_max_c: int = 18,
    temp_felt_min_c: int = 10,
    wind_kn_low: int = 4,
    wind_kn_high: int = 10,
    gust_kn_max: int = 22,
    sunrise: str | None = "07:03",
    sunset: str | None = "17:30",
    day: ForecastDay | None = None,
) -> Forecast:
    primary = DaySummary(
        label="Today", weekday="Sun",
        temp_max_c=21, temp_min_c=15,
        wind_kn_max=10,
        rain_mm_low=rain_mm_low, rain_mm_high=rain_mm_high,
        sun_hours=2.0,
    )
    return Forecast(
        day=day or ForecastDay.today(date(2026, 5, 3)),
        primary=primary, next_day_preview=next_day_preview,
        peak_rain_mm=peak_mm, peak_rain_time=peak_time,
        uv_index=uv_index,
        temp_felt_max_c=temp_felt_max_c, temp_felt_min_c=temp_felt_min_c,
        wind_kn_low=wind_kn_low, wind_kn_high=wind_kn_high, gust_kn_max=gust_kn_max,
        sunrise=sunrise, sunset=sunset,
    )


def test_render_full_template():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now, _SOURCE_URL)

    # Header line — no "Melbourne CBD" (channel name covers location).
    assert "Melbourne CBD" not in out
    assert "Sunday" in out
    assert "3 May" in out

    # Felt-temp headline (no <b>, hand+thermometer icon)
    assert "🤚🌡 High 18° / Low 10°" in out

    # Rain line — peak mm with intensity band, plain (un-bolded) value.
    # The band emoji + "@HH:00" already convey "peak hourly", so the
    # literal word "Peak" is dropped.
    assert "10–20mm" in out                 # en-dash
    assert "🟡 1.5mm @12:00" in out
    assert "Peak" not in out
    assert "<b>1.5mm</b>" not in out

    # Wind (knots) — hourly range + peak gust, all plain text
    assert "💨 Wind 4–10kn · gusts to 22kn" in out

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
    # The whole rain line is just "☔ No rain" — no peak tail appended.
    rain_line = next(line for line in out.splitlines() if line.startswith("☔"))
    assert rain_line == "☔ No rain"
    # Other lines still present
    assert "🤚🌡" in out
    assert "💨" in out


def test_omits_peak_tail_when_peak_mm_zero_but_range_nonzero():
    # Mirrors the current fixture's situation: 47% probability but every
    # hourly mm cell is empty/0, while the daily range is 0–2mm.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(rain_mm_low=0.0, rain_mm_high=2.0, peak_mm=0.0, peak_time="")
    out = render(f, now, _SOURCE_URL)
    rain_line = next(line for line in out.splitlines() if line.startswith("☔"))
    assert rain_line == "☔ Rain 0–2mm"


def test_render_peak_mm_formats_one_decimal():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(peak_mm=1.5, peak_time="14:00"), now, _SOURCE_URL)
    assert "🟡 1.5mm @14:00" in out
    assert "<b>1.5mm</b>" not in out


def test_render_peak_mm_strips_trailing_zero():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(peak_mm=12.0, peak_time="14:00"), now, _SOURCE_URL)
    assert "🔴 12mm @14:00" in out
    assert "12.0mm" not in out
    assert "<b>12mm</b>" not in out


def test_render_collapses_equal_wind_range():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(
        _make_forecast(wind_kn_low=7, wind_kn_high=7, gust_kn_max=15),
        now,
        _SOURCE_URL,
    )
    assert "💨 Wind 7kn · gusts to 15kn" in out
    assert "7–7kn" not in out


def test_render_wind_line_is_plain_text():
    # Both wind and gust values render without <b> tags.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(
        _make_forecast(wind_kn_low=4, wind_kn_high=10, gust_kn_max=22),
        now,
        _SOURCE_URL,
    )
    wind_line = next(line for line in out.splitlines() if line.startswith("💨"))
    assert "<b>" not in wind_line
    assert "</b>" not in wind_line


def test_drops_sun_line_when_sun_times_missing():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(sunrise=None, sunset=None)
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
    f = _make_forecast(day=_TOMORROW_DAY, next_day_preview=None)
    out = render(f, now, _SOURCE_URL)

    # Header: "🌦 Tomorrow, Monday 11 May" — no "Melbourne CBD".
    assert "Melbourne CBD" not in out
    assert "Tomorrow, Monday" in out
    assert "11 May" in out
    # Today-mode header pattern must NOT appear (no plain "Sunday, 10 May").
    assert "Sunday, 10 May" not in out


def test_render_tomorrow_mode_omits_preview_line():
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(day=_TOMORROW_DAY, next_day_preview=None)
    out = render(f, now, _SOURCE_URL)
    assert "<i>Tomorrow:</i>" not in out


def test_render_tomorrow_mode_keeps_run_time_in_updated_line():
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(day=_TOMORROW_DAY, next_day_preview=None)
    out = render(f, now, _SOURCE_URL)
    # "Updated 18:00 AEST" — the actual run time, not the forecast date.
    assert "Updated 18:00" in out


def test_render_tomorrow_mode_uses_forecast_sun_times_verbatim():
    # Sun times now come straight off the forecast (scraped from the
    # ?day=2 page in tomorrow-mode), not from any per-date lookup —
    # the caption just renders whatever strings are on the dataclass.
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(day=_TOMORROW_DAY, next_day_preview=None, sunrise="06:55", sunset="17:25")
    out = render(f, now, _SOURCE_URL)
    assert "🌅 06:55" in out
    assert "🌇 17:25" in out


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
    assert "🟢 UV index 2 (Low)" in out


def test_render_includes_uv_line_tomorrow_mode():
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(day=_TOMORROW_DAY, next_day_preview=None, uv_index=7)
    out = render(f, now, _SOURCE_URL)
    assert "🟠 UV index 7 (High)" in out


def test_render_uv_line_appears_after_sun_line():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(uv_index=4), now, _SOURCE_URL)
    lines = out.splitlines()
    sun_idx = next(i for i, line in enumerate(lines) if "Sun 2h" in line)
    uv_idx = next(i for i, line in enumerate(lines) if "UV index" in line)
    assert uv_idx == sun_idx + 1, (
        f"UV line should immediately follow sun line; "
        f"got sun at {sun_idx}, UV at {uv_idx}"
    )


def test_render_uv_line_appears_after_wind_when_sun_unavailable():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(uv_index=4, sunrise=None, sunset=None)
    out = render(f, now, _SOURCE_URL)
    assert "☀" not in out  # sun line dropped
    lines = out.splitlines()
    wind_idx = next(i for i, line in enumerate(lines) if line.startswith("💨"))
    uv_idx = next(i for i, line in enumerate(lines) if "UV index" in line)
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


@pytest.mark.parametrize(
    "peak_mm,expected_emoji",
    [
        (0.1, "🟢"),
        (1.0, "🟢"),
        (1.01, "🟡"),
        (3.5, "🟡"),
        (5.0, "🟡"),
        (5.01, "🟠"),
        (7.5, "🟠"),
        (10.0, "🟠"),
        (10.01, "🔴"),
        (50.0, "🔴"),
    ],
)
def test_rain_band_maps_peak_to_emoji(peak_mm, expected_emoji):
    from burevestnik.caption import _rain_band
    assert _rain_band(peak_mm) == expected_emoji


def test_render_escapes_html_in_source_url():
    # URLs with `&` are valid; the caption must escape them so Telegram's
    # HTML parse_mode doesn't reject the message.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now, "https://example.com/x?a=1&b=2&c=<3>")
    assert "https://example.com/x?a=1&amp;b=2&amp;c=&lt;3&gt;" in out
    # Raw ampersand must not appear inside the href.
    assert 'href="https://example.com/x?a=1&b=2' not in out


def test_render_uv_line_present_at_uv_zero():
    # UV 0 still renders — the layout is unconditional.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(uv_index=0), now, _SOURCE_URL)
    assert "🟢 UV index 0 (Low)" in out


# ── Headline condition emoji ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "title,expected",
    [
        # Every label observed in tests/fixtures/meteoblue.html.
        ("Clear, cloudless sky",                  "☀"),
        ("Clear and few clouds",                  "🌤"),   # "few clouds" wins before "clear"
        ("Partly cloudy",                         "⛅"),
        ("Overcast",                              "☁"),
        ("Overcast with rain",                    "🌧"),
        ("Overcast with occasional rain",         "🌦"),
        ("Mostly cloudy with occasional rain",    "🌦"),
        ("Mostly cloudy",                         "🌥"),
        # Plausible labels not in the fixture — keyword priority survives.
        ("Mostly cloudy with thunderstorms",      "⛈"),   # thunder beats everything
        ("Light rain",                            "🌦"),
        ("Heavy rain",                            "🌧"),
        ("Few showers",                           "🌦"),
        ("Fog",                                   "🌫"),
        ("Mist",                                  "🌫"),
        ("Light snow showers",                    "🌨"),  # snow beats rain sub-rule
        ("Sleet",                                 "🌨"),
        ("Drizzle",                               "🌧"),
        ("Light drizzle",                         "🌦"),
        # Case-insensitivity — meteoblue is consistent but be defensive.
        ("PARTLY CLOUDY",                         "⛅"),
        # Fallback cases.
        ("",                                      "🌦"),
        ("Some weather we've never seen",         "🌦"),
    ],
)
def test_condition_emoji_maps_title_to_emoji(title, expected):
    from burevestnik.caption import _condition_emoji
    assert _condition_emoji(title) == expected


def test_condition_emoji_none_falls_back_to_default():
    from burevestnik.caption import _condition_emoji
    assert _condition_emoji(None) == "🌦"


def test_render_header_uses_condition_emoji_today_mode():
    # Partly cloudy → ⛅ on the today header line.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast()
    f = Forecast(
        day=f.day,
        primary=DaySummary(
            label=f.primary.label, weekday=f.primary.weekday,
            temp_max_c=f.primary.temp_max_c, temp_min_c=f.primary.temp_min_c,
            wind_kn_max=f.primary.wind_kn_max,
            rain_mm_low=f.primary.rain_mm_low, rain_mm_high=f.primary.rain_mm_high,
            sun_hours=f.primary.sun_hours,
            condition="Partly cloudy",
        ),
        next_day_preview=f.next_day_preview,
        peak_rain_mm=f.peak_rain_mm, peak_rain_time=f.peak_rain_time,
        uv_index=f.uv_index,
        temp_felt_max_c=f.temp_felt_max_c, temp_felt_min_c=f.temp_felt_min_c,
        wind_kn_low=f.wind_kn_low, wind_kn_high=f.wind_kn_high, gust_kn_max=f.gust_kn_max,
        sunrise=f.sunrise, sunset=f.sunset,
    )
    out = render(f, now, _SOURCE_URL)
    lines = out.splitlines()
    assert lines[0].startswith("⛅ ")
    assert "Melbourne CBD" not in out


def test_render_header_uses_condition_emoji_tomorrow_mode():
    # In tomorrow-mode the same emoji-pick logic runs against forecast.primary.condition.
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(day=_TOMORROW_DAY, next_day_preview=None)
    f = Forecast(
        day=_TOMORROW_DAY,
        primary=DaySummary(
            label="Tomorrow", weekday="Mon",
            temp_max_c=f.primary.temp_max_c, temp_min_c=f.primary.temp_min_c,
            wind_kn_max=f.primary.wind_kn_max,
            rain_mm_low=f.primary.rain_mm_low, rain_mm_high=f.primary.rain_mm_high,
            sun_hours=f.primary.sun_hours,
            condition="Overcast with rain",
        ),
        next_day_preview=None,
        peak_rain_mm=f.peak_rain_mm, peak_rain_time=f.peak_rain_time,
        uv_index=f.uv_index,
        temp_felt_max_c=f.temp_felt_max_c, temp_felt_min_c=f.temp_felt_min_c,
        wind_kn_low=f.wind_kn_low, wind_kn_high=f.wind_kn_high, gust_kn_max=f.gust_kn_max,
        sunrise=f.sunrise, sunset=f.sunset,
    )
    out = render(f, now, _SOURCE_URL)
    lines = out.splitlines()
    assert lines[0].startswith("🌧 ")


def test_render_header_falls_back_when_condition_missing():
    # condition=None must not crash the render; falls back to default 🌦.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now, _SOURCE_URL)
    lines = out.splitlines()
    assert lines[0].startswith("🌦 ")


def test_no_blank_line_between_header_and_felt_temp():
    # Headline (line 0) flows directly into the felt-temp line (line 1) — no
    # gap — so iPhone push-notification summaries can show both at a glance.
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now, _SOURCE_URL)
    lines = out.splitlines()
    assert lines[1].startswith("🤚🌡"), f"line[1] should be the felt-temp line; got: {lines[1]!r}"


def test_no_blank_line_between_header_and_felt_temp_tomorrow_mode():
    now = datetime(2026, 5, 10, 18, 0, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(day=_TOMORROW_DAY, next_day_preview=None)
    out = render(f, now, _SOURCE_URL)
    lines = out.splitlines()
    assert lines[1].startswith("🤚🌡"), f"line[1] should be the felt-temp line; got: {lines[1]!r}"


# ── 5-day outlook caption ────────────────────────────────────────────────

_FIXTURE = (Path(__file__).parent / "fixtures" / "meteoblue.html").read_text(encoding="utf-8")


def _outlook_day(weekday, tmax, tmin, rlow, rhigh, sun, condition):
    return DaySummary(
        label="", weekday=weekday,
        temp_max_c=tmax, temp_min_c=tmin,
        wind_kn_max=0,
        rain_mm_low=rlow, rain_mm_high=rhigh,
        sun_hours=sun, condition=condition,
    )


def test_render_outlook_formats_each_day_on_one_line():
    from burevestnik.caption import render_outlook
    now = datetime(2026, 5, 7, 4, 17, tzinfo=ZoneInfo("Australia/Melbourne"))
    days = [
        _outlook_day("Thu", 17, 10, 1.0, 3.0, 4.0, "Mostly cloudy with occasional rain"),
        _outlook_day("Fri", 18, 15, 0.0, 0.0, 8.0, "Clear, cloudless sky"),
    ]
    out = render_outlook(days, now, _SOURCE_URL)
    lines = out.splitlines()
    assert lines[0] == "🌦 Thu 17°/10° ☔ 1–3mm ☀ 4h"   # rain+occasional → 🌦, en-dash
    assert lines[1] == "☀ Fri 18°/15° no rain ☀ 8h"      # high==0 → "no rain"


def test_render_outlook_has_no_header_line():
    from burevestnik.caption import render_outlook
    now = datetime(2026, 5, 7, 4, 17, tzinfo=ZoneInfo("Australia/Melbourne"))
    days = [_outlook_day("Thu", 17, 10, 0.0, 0.0, 4.0, "Clear, cloudless sky")]
    out = render_outlook(days, now, _SOURCE_URL)
    # First line is a day, not a title.
    assert out.splitlines()[0].startswith("☀ Thu ")
    assert "outlook" not in out.lower()


def test_render_outlook_footer_matches_daily_caption():
    from burevestnik.caption import render_outlook
    now = datetime(2026, 5, 7, 4, 17, tzinfo=ZoneInfo("Australia/Melbourne"))
    days = [_outlook_day("Thu", 17, 10, 0.0, 0.0, 4.0, "Clear, cloudless sky")]
    out = render_outlook(days, now, _SOURCE_URL)
    lines = out.splitlines()
    assert lines[-2] == ""  # blank line before footer
    assert lines[-1].startswith("<i>Updated 04:17 ")
    assert f'<a href="{_SOURCE_URL}">meteoblue</a>' in out


def test_render_outlook_escapes_url():
    from burevestnik.caption import render_outlook
    now = datetime(2026, 5, 7, 4, 17, tzinfo=ZoneInfo("Australia/Melbourne"))
    days = [_outlook_day("Thu", 17, 10, 0.0, 0.0, 4.0, "Clear, cloudless sky")]
    out = render_outlook(days, now, "https://example.com/x?a=1&b=2")
    assert "https://example.com/x?a=1&amp;b=2" in out


def test_render_outlook_under_1024_chars():
    from burevestnik.caption import render_outlook
    from burevestnik.parse import parse_days
    now = datetime(2026, 5, 7, 4, 17, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render_outlook(parse_days(_FIXTURE, 5), now, _SOURCE_URL)
    assert len(out) <= 1024


def test_render_outlook_against_fixture():
    from burevestnik.caption import render_outlook
    from burevestnik.parse import parse_days
    now = datetime(2026, 5, 7, 4, 17, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render_outlook(parse_days(_FIXTURE, 5), now, _SOURCE_URL)
    assert "⛅ Tue 15°/12° no rain ☀ 2h" in out
    assert "⛅ Wed 18°/10° ☔ 2–5mm ☀ 4h" in out
    assert "🌧 Thu 10°/8° ☔ 5–10mm ☀ 0h" in out
    assert "🌦 Fri 15°/9° ☔ 2–5mm ☀ 2h" in out
    assert "🌦 Sat 16°/12° ☔ 0–2mm ☀ 0h" in out
