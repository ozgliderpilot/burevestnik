from pathlib import Path
import pytest
from burevestnik.parse import parse_day, extract
from burevestnik.models import Forecast

FIXTURE = (Path(__file__).parent / "fixtures" / "meteoblue.html").read_text(encoding="utf-8")


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


def test_parse_day_raises_on_missing_selector():
    with pytest.raises(ValueError, match="no element"):
        parse_day(FIXTURE, "#day99")


def test_extract_returns_full_forecast():
    f = extract(FIXTURE)
    assert isinstance(f, Forecast)
    assert f.today.label == "Today"
    assert f.tomorrow.label == "Tomorrow"
    # Fixture's tr.precip is all-empty, so peak mm is 0.0.
    assert f.peak_rain_mm == 0.0
    assert f.peak_rain_time == ""
    # Fixture felt-temp row max/min: 13 / 10.
    assert f.temp_felt_max_c == 13
    assert f.temp_felt_min_c == 10


def test_extract_for_tomorrow_uses_day2_as_primary():
    f = extract(FIXTURE, for_tomorrow=True)
    # #day2's long-label is "Tomorrow" in the meteoblue fixture; with
    # for_tomorrow=True we promote that day to the primary slot.
    assert f.today.label == "Tomorrow"


def test_extract_for_tomorrow_sets_tomorrow_field_to_none():
    f = extract(FIXTURE, for_tomorrow=True)
    assert f.tomorrow is None
    # Sanity: peak rain still resolves (parser ignores the flag for hourly
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


def test_extract_populates_uv_index_today_mode():
    f = extract(FIXTURE)
    assert f.uv_index == 2


def test_extract_populates_uv_index_tomorrow_mode():
    # Same fixture so same value, but verify the path doesn't accidentally
    # zero-out UV when for_tomorrow=True.
    f = extract(FIXTURE, for_tomorrow=True)
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
      <tr><th></th><th>1000</th><th>1100</th><th>1200</th></tr>
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
      <tr><th></th><th>1000</th><th>1100</th><th>1200</th></tr>
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
      <tr><th></th><td></td><td>0100</td><td>0200</td></tr>
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
      <tr><th></th><th>0100</th><th>0200</th></tr>
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
    f = extract(FIXTURE)
    assert f.wind_kn_low == 2
    assert f.wind_kn_high == 7
    assert f.gust_kn_max == 22
