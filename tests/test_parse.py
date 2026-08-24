from datetime import date
from pathlib import Path
import pytest
from burevestnik.parse import parse_day, extract
from burevestnik.models import Forecast, ForecastDay

FIXTURE = (Path(__file__).parent / "fixtures" / "meteoblue.html").read_text(encoding="utf-8")
_TODAY = ForecastDay.today(date(2026, 5, 5))
_TOMORROW = ForecastDay.tomorrow(date(2026, 5, 6))


def test_parse_day_today_extracts_temps():
    day = parse_day(FIXTURE, "#day1")
    assert isinstance(day.temp_max_c, int)
    assert isinstance(day.temp_min_c, int)
    assert day.temp_max_c >= day.temp_min_c
    assert -20 <= day.temp_min_c <= 50    # sanity range for Melbourne
    assert -20 <= day.temp_max_c <= 50


def test_parse_day_today_extracts_wind_and_sun():
    day = parse_day(FIXTURE, "#day1")
    assert day.wind_kn_max > 0
    assert day.sun_hours >= 0


def test_parse_day_today_extracts_rain_range():
    day = parse_day(FIXTURE, "#day1")
    assert day.rain_mm_low >= 0
    assert day.rain_mm_high >= day.rain_mm_low


def test_parse_day_tomorrow_has_label():
    day = parse_day(FIXTURE, "#day2")
    # Tomorrow tab includes the literal string "Tomorrow"
    assert day.label == "Tomorrow"
    # Loose sanity: rain values are non-negative and the high is at least the low.
    # (We don't lock specific values because the fixture varies day-to-day.)
    assert day.rain_mm_low >= 0
    assert day.rain_mm_high >= day.rain_mm_low


def test_parse_day_high_wind_range_without_kn_unit():
    # On high-wind days meteoblue drops the inline "kn" unit and renders a
    # "speed-gust" range (e.g. "13-34" = 13 kn wind, 34 kn gust); the unit
    # moves into the div's title attribute. parse_day must read the dedicated
    # div.wind and resolve wind_kn_max to the wind speed (lower bound), not the
    # gust. Regression for the #day2 high-wind crash.
    html = """
    <html><body>
    <div id="day2">
      <div class="tab-day-short">Mon</div>
      <div class="tab-day-long">Tomorrow</div>
      <div class="temps">
        <div class="tab-temp-max">13 °C</div>
        <div class="tab-temp-min">9 °C</div>
      </div>
      <div class="data">
        <div class="wind" title="Wind speed (kn)">
          <span class="glyph winddir N"></span>
          13-34
        </div>
        <div class="tab-precip"><span class="glyph rain"></span>5-10 mm</div>
        <div class="tab-sun"><span class="glyph sunshine"></span>2 h</div>
      </div>
    </div>
    </body></html>
    """
    day = parse_day(html, "#day2")
    assert day.wind_kn_max == 13
    assert day.rain_mm_low == 5.0
    assert day.rain_mm_high == 10.0
    # Temps and sun are read from their dedicated divs too, so the high-wind
    # range concatenation can't bleed into them either.
    assert day.temp_max_c == 13
    assert day.temp_min_c == 9
    assert day.sun_hours == 2.0


def test_parse_day_prefers_dedicated_divs_over_flattened_text():
    # Each numeric field is isolated to its own child element, so a stray
    # number elsewhere in the tab's flattened text must not be picked up.
    # The dedicated divs say 13°/9°, 8 kn, 5 mm, 2 h; the decoy text would
    # mislead an order-dependent flattened-text scan.
    html = """
    <html><body>
    <div id="day2">
      <div class="tab-day-short">Mon</div>
      <div class="tab-day-long">Tomorrow</div>
      <div class="decoy">99 °C 77 °C 88 kn 44 mm 66 h</div>
      <div class="temps">
        <div class="tab-temp-max">13 °C</div>
        <div class="tab-temp-min">9 °C</div>
      </div>
      <div class="data">
        <div class="wind" title="Wind speed"><span class="glyph"></span>8 kn</div>
        <div class="tab-precip"><span class="glyph rain"></span>5 mm</div>
        <div class="tab-sun"><span class="glyph sunshine"></span>2 h</div>
      </div>
    </div>
    </body></html>
    """
    day = parse_day(html, "#day2")
    assert (day.temp_max_c, day.temp_min_c) == (13, 9)
    assert day.wind_kn_max == 8
    assert (day.rain_mm_low, day.rain_mm_high) == (5.0, 5.0)
    assert day.sun_hours == 2.0


def test_parse_day_reads_single_wind_value_from_div():
    # Normal-wind day: div.wind text is "8 kn", giving wind_kn_max == 8.
    html = """
    <html><body>
    <div id="day1">
      <div class="tab-day-short">Sun</div>
      <div class="tab-day-long">Today</div>
      <div class="temps">
        <div class="tab-temp-max">14 °C</div>
        <div class="tab-temp-min">10 °C</div>
      </div>
      <div class="data">
        <div class="wind" title="Wind speed">
          <span class="glyph winddir NW"></span>
          8 kn
        </div>
        <div class="tab-precip"><span class="glyph rain"></span>-</div>
        <div class="tab-sun"><span class="glyph sunshine"></span>4 h</div>
      </div>
    </div>
    </body></html>
    """
    day = parse_day(html, "#day1")
    assert day.wind_kn_max == 8


def test_parse_day_raises_on_missing_selector():
    with pytest.raises(ValueError, match="no element"):
        parse_day(FIXTURE, "#day99")


def test_extract_returns_full_forecast():
    f = extract(FIXTURE, day=_TODAY)
    assert isinstance(f, Forecast)
    assert f.day == _TODAY
    assert f.primary.label == "Today"
    assert f.next_day_preview.label == "Tomorrow"
    # Fixture's tr.precip is all-empty, so peak mm is 0.0.
    assert f.peak_rain_mm == 0.0
    assert f.peak_rain_time == ""
    # Fixture felt-temp row max/min: 13 / 10.
    assert f.temp_felt_max_c == 13
    assert f.temp_felt_min_c == 10


def test_extract_tomorrow_uses_day2_as_primary():
    f = extract(FIXTURE, day=_TOMORROW)
    # #day2's long-label is "Tomorrow" in the meteoblue fixture; Forecast
    # day Tomorrow promotes that tab to the primary slot.
    assert f.day == _TOMORROW
    assert f.primary.label == "Tomorrow"


def test_extract_tomorrow_sets_next_day_preview_to_none():
    f = extract(FIXTURE, day=_TOMORROW)
    assert f.next_day_preview is None
    # Sanity: peak rain still resolves (parser ignores Forecast day for hourly
    # — the page swap from ?day=2 is the runtime mechanism).
    assert f.peak_rain_mm >= 0.0


def test_parse_uv_extracts_fixture_value():
    from burevestnik.parse import parse_uv
    assert parse_uv(FIXTURE) == 2


def test_parse_uv_raises_on_missing_element():
    from burevestnik.parse import parse_uv
    html = "<html><body><div>no uv here</div></body></html>"
    with pytest.raises(ValueError, match="uv-index"):
        parse_uv(html)


def test_parse_uv_raises_when_text_unparseable():
    from burevestnik.parse import parse_uv
    html = '<html><body><div class="uv-index"><span class="uv-risk"></span>no number</div></body></html>'
    with pytest.raises(ValueError, match="UV"):
        parse_uv(html)


def test_parse_uv_handles_extra_whitespace():
    # meteoblue's actual markup has trailing whitespace inside the div ("UV 2   ").
    # Make sure normalisation matches parse_day's behaviour.
    from burevestnik.parse import parse_uv
    html = '<html><body><div class="uv-index"><span class="uv-risk"></span>\n    UV   7   \n</div></body></html>'
    assert parse_uv(html) == 7


def test_extract_populates_uv_index_today():
    f = extract(FIXTURE, day=_TODAY)
    assert f.uv_index == 2


def test_extract_populates_uv_index_tomorrow():
    # Same fixture so same value, but verify the path doesn't accidentally
    # zero-out UV when Forecast day is Tomorrow.
    f = extract(FIXTURE, day=_TOMORROW)
    assert f.uv_index == 2


def test_parse_temp_felt_extracts_fixture_max_min():
    from burevestnik.parse import parse_temp_felt
    hi, lo = parse_temp_felt(FIXTURE)
    # Locked to the captured fixture's actual felt-temp row.
    assert hi == 13
    assert lo == 10


def test_parse_temp_felt_handles_negative_values():
    from burevestnik.parse import parse_temp_felt
    html = """
    <html><body>
    <table class="hourlywind">
      <tr><th></th><th>0100</th><th>0200</th><th>0300</th></tr>
      <tr class="temperature-felt">
        <th title="Temperature felt (°C)"><span class="glyph"></span></th>
        <td>-3°</td><td>-1°</td><td>2°</td>
      </tr>
    </table>
    </body></html>
    """
    hi, lo = parse_temp_felt(html)
    assert hi == 2
    assert lo == -3


def test_parse_temp_felt_raises_when_row_missing():
    from burevestnik.parse import parse_temp_felt
    html = '<html><body><table class="hourlywind"><tr><th></th><td>nope</td></tr></table></body></html>'
    with pytest.raises(ValueError, match="temperature-felt"):
        parse_temp_felt(html)


def test_parse_temp_felt_raises_when_no_numeric_cells():
    from burevestnik.parse import parse_temp_felt
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="temperature-felt"><th></th><td></td><td></td></tr>
    </table>
    </body></html>
    """
    with pytest.raises(ValueError, match="temperature-felt"):
        parse_temp_felt(html)


def test_parse_peak_rain_mm_returns_zero_for_dry_fixture():
    # Fixture has tr.precip with all-empty <span>s — no hourly rain mm.
    from burevestnik.parse import parse_peak_rain_mm
    mm, t = parse_peak_rain_mm(FIXTURE)
    assert mm == 0.0
    assert t == ""


def test_parse_peak_rain_mm_picks_max_value():
    from burevestnik.parse import parse_peak_rain_mm
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="times"><th></th><th>1000</th><th>1100</th><th>1200</th></tr>
      <tr class="precip">
        <th>mm</th>
        <td><span>0.5</span></td>
        <td><span>1.5</span></td>
        <td><span>0.2</span></td>
      </tr>
    </table>
    </body></html>
    """
    mm, t = parse_peak_rain_mm(html)
    assert mm == 1.5
    assert t == "11:00"


def test_parse_peak_rain_mm_breaks_ties_to_earliest():
    from burevestnik.parse import parse_peak_rain_mm
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="times"><th></th><th>1000</th><th>1100</th><th>1200</th></tr>
      <tr class="precip">
        <th>mm</th>
        <td><span>1.5</span></td>
        <td><span>2.0</span></td>
        <td><span>2.0</span></td>
      </tr>
    </table>
    </body></html>
    """
    mm, t = parse_peak_rain_mm(html)
    assert mm == 2.0
    assert t == "11:00"


def test_parse_peak_rain_mm_handles_unlabeled_midnight_column():
    # An empty <td> for the midnight column whose
    # label is implicit. If midnight is the peak, time is "00:00".
    from burevestnik.parse import parse_peak_rain_mm
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="times"><th></th><td></td><td>0100</td><td>0200</td></tr>
      <tr class="precip">
        <th>mm</th>
        <td><span>3.0</span></td>
        <td><span>1.0</span></td>
        <td><span>0.5</span></td>
      </tr>
    </table>
    </body></html>
    """
    mm, t = parse_peak_rain_mm(html)
    assert mm == 3.0
    assert t == "00:00"


def test_parse_peak_rain_mm_returns_empty_when_all_empty_cells():
    from burevestnik.parse import parse_peak_rain_mm
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="times"><th></th><th>0100</th><th>0200</th></tr>
      <tr class="precip">
        <th>mm</th>
        <td><span></span></td>
        <td><span></span></td>
      </tr>
    </table>
    </body></html>
    """
    mm, t = parse_peak_rain_mm(html)
    assert mm == 0.0
    assert t == ""


def test_parse_peak_rain_mm_raises_when_row_missing():
    from burevestnik.parse import parse_peak_rain_mm
    html = '<html><body><table class="hourlywind"><tr><th></th></tr></table></body></html>'
    with pytest.raises(ValueError, match="precip"):
        parse_peak_rain_mm(html)


def test_parse_peak_rain_mm_raises_when_times_row_missing():
    # If the precip row is present but the tr.times header row is not, the
    # parser can no longer align cells to hour labels and must fail loudly
    # rather than silently mislabel the peak hour.
    from burevestnik.parse import parse_peak_rain_mm
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="precip">
        <th>mm</th>
        <td><span>1.0</span></td>
      </tr>
    </table>
    </body></html>
    """
    with pytest.raises(ValueError, match="tr.times"):
        parse_peak_rain_mm(html)


def test_parse_wind_range_extracts_fixture_min_max():
    from burevestnik.parse import parse_wind_range
    lo, hi = parse_wind_range(FIXTURE)
    # Fixture's tr.windspeed: 7,7,6,6,6,6,6,6,6,6,6,6,6,5,5,5,4,3,3,2,2,2,2,3.
    assert lo == 2
    assert hi == 7


def test_parse_wind_range_handles_constant_row():
    from burevestnik.parse import parse_wind_range
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="windspeed"><th></th><td>5</td><td>5</td><td>5</td></tr>
    </table>
    </body></html>
    """
    lo, hi = parse_wind_range(html)
    assert lo == 5
    assert hi == 5


def test_parse_wind_range_raises_when_row_missing():
    from burevestnik.parse import parse_wind_range
    html = '<html><body><table class="hourlywind"><tr><th></th><td>nope</td></tr></table></body></html>'
    with pytest.raises(ValueError, match="windspeed"):
        parse_wind_range(html)


def test_parse_wind_range_raises_when_no_numeric_cells():
    from burevestnik.parse import parse_wind_range
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="windspeed"><th></th><td></td><td></td></tr>
    </table>
    </body></html>
    """
    with pytest.raises(ValueError, match="windspeed"):
        parse_wind_range(html)


def test_parse_peak_gust_kn_extracts_fixture_value():
    from burevestnik.parse import parse_peak_gust_kn
    # Fixture's tr.windgust peaks at 22 in the first cell.
    assert parse_peak_gust_kn(FIXTURE) == 22


def test_parse_peak_gust_kn_picks_max_value():
    from burevestnik.parse import parse_peak_gust_kn
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="windgust"><th></th><td>10</td><td>30</td><td>15</td></tr>
    </table>
    </body></html>
    """
    assert parse_peak_gust_kn(html) == 30


def test_parse_peak_gust_kn_raises_when_row_missing():
    from burevestnik.parse import parse_peak_gust_kn
    html = '<html><body><table class="hourlywind"><tr><th></th><td>5</td></tr></table></body></html>'
    with pytest.raises(ValueError, match="windgust"):
        parse_peak_gust_kn(html)


def test_parse_peak_gust_kn_raises_when_no_numeric_cells():
    from burevestnik.parse import parse_peak_gust_kn
    html = """
    <html><body>
    <table class="hourlywind">
      <tr class="windgust"><th></th><td></td></tr>
    </table>
    </body></html>
    """
    with pytest.raises(ValueError, match="windgust"):
        parse_peak_gust_kn(html)


def test_extract_populates_wind_and_gust_fields():
    f = extract(FIXTURE, day=_TODAY)
    assert f.wind_kn_low == 2
    assert f.wind_kn_high == 7
    assert f.gust_kn_max == 22


def test_parse_sun_times_extracts_fixture_values():
    from burevestnik.parse import parse_sun_times
    rise, sset = parse_sun_times(FIXTURE)
    # Fixture's <div title="Sunrise/Sunset"> blocks carry these times.
    assert rise == "07:03"
    assert sset == "17:30"


def test_parse_sun_times_returns_none_when_blocks_missing():
    from burevestnik.parse import parse_sun_times
    html = "<html><body><div>no sun blocks here</div></body></html>"
    assert parse_sun_times(html) == (None, None)


def test_parse_sun_times_returns_none_when_only_sunrise_present():
    from burevestnik.parse import parse_sun_times
    html = '<html><body><div title="Sunrise">07:08</div></body></html>'
    assert parse_sun_times(html) == (None, None)


def test_parse_sun_times_returns_none_when_time_unparseable():
    from burevestnik.parse import parse_sun_times
    html = (
        '<html><body>'
        '<div title="Sunrise">no time</div>'
        '<div title="Sunset">no time</div>'
        '</body></html>'
    )
    assert parse_sun_times(html) == (None, None)


def test_extract_populates_sun_times():
    f = extract(FIXTURE, day=_TODAY)
    assert f.sunrise == "07:03"
    assert f.sunset == "17:30"


def test_parse_day_populates_condition_from_pictogram_alt():
    # #day1's .weather-pictogram-wrapper.day img has alt="Partly cloudy".
    day = parse_day(FIXTURE, "#day1")
    assert day.condition == "Partly cloudy"


def test_parse_day_populates_condition_for_day2():
    # #day2 also carries a day-pictogram; in tomorrow-mode this is what
    # drives the headline emoji.
    day = parse_day(FIXTURE, "#day2")
    assert day.condition == "Partly cloudy"


def test_parse_day_condition_is_none_when_pictogram_missing():
    html = """
    <html><body>
    <div id="day1">
      <span class="tab-day-short">Mon</span>
      <span class="tab-day-long">Today</span>
      19 °C 14 °C 7 kn 0-2 mm 5 h
    </div>
    </body></html>
    """
    day = parse_day(html, "#day1")
    assert day.condition is None


def test_extract_populates_primary_condition():
    f = extract(FIXTURE, day=_TODAY)
    assert f.primary.condition == "Partly cloudy"


def test_extract_tomorrow_populates_primary_condition_from_day2():
    f = extract(FIXTURE, day=_TOMORROW)
    assert f.primary.condition == "Partly cloudy"


def test_extract_requires_forecast_day():
    with pytest.raises(TypeError):
        extract(FIXTURE)


def test_extract_populates_next_day_preview_condition():
    # Symmetry: even though the caption doesn't render it today, the parser
    # fills in condition for the next-day preview so the dataclass is uniform.
    f = extract(FIXTURE, day=_TODAY)
    assert f.next_day_preview is not None
    assert f.next_day_preview.condition == "Partly cloudy"


def test_parse_days_returns_five_summaries_in_order():
    from burevestnik.parse import parse_days
    days = parse_days(FIXTURE, 5)
    assert len(days) == 5
    assert [d.weekday for d in days] == ["Tue", "Wed", "Thu", "Fri", "Sat"]


def test_parse_days_reads_each_days_fields():
    from burevestnik.parse import parse_days
    days = parse_days(FIXTURE, 5)
    # Locked to the captured fixture's #day1..#day5 tabs.
    assert (days[0].temp_max_c, days[0].temp_min_c) == (15, 12)
    assert (days[0].rain_mm_low, days[0].rain_mm_high) == (0.0, 0.0)  # "-" → dry
    assert days[0].sun_hours == 2.0
    assert days[0].condition == "Partly cloudy"
    assert (days[2].temp_max_c, days[2].temp_min_c) == (10, 8)
    assert (days[2].rain_mm_low, days[2].rain_mm_high) == (5.0, 10.0)
    assert days[2].condition == "Overcast with rain"
    assert (days[4].temp_max_c, days[4].temp_min_c) == (16, 12)
    assert (days[4].rain_mm_low, days[4].rain_mm_high) == (0.0, 2.0)


def test_parse_days_default_count_is_five():
    from burevestnik.parse import parse_days
    assert len(parse_days(FIXTURE)) == 5


def test_parse_days_raises_when_a_tab_is_missing():
    from burevestnik.parse import parse_days
    with pytest.raises(ValueError, match="no element"):
        parse_days(FIXTURE, 15)  # fixture has #day1..#day14
