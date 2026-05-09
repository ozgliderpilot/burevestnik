from pathlib import Path
import pytest
from burevestnik.parse import parse_day, parse_peak_rain, extract
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


def test_parse_peak_rain_returns_int_and_hh_mm():
    pct, t = parse_peak_rain(FIXTURE)
    assert isinstance(pct, int)
    assert 0 <= pct <= 100
    if pct > 0:
        # "HH:00"
        assert len(t) == 5 and t[2] == ":"
        hh = int(t[:2])
        assert 0 <= hh <= 23
    # Locked to the captured fixture's actual peak (re-capture if this fails).
    assert pct == 47
    assert t == "00:00"


def test_parse_peak_rain_no_table_raises():
    with pytest.raises(ValueError, match="hourlywind"):
        parse_peak_rain("<html><body>nope</body></html>")


def test_parse_peak_rain_zero_percent_returns_empty_time():
    # Synthesize a stripped-down hourly table with all zeros.
    html = """
    <html><body>
    <table class="hourlywind">
      <tr><th></th><th></th><th>0100</th><th>0200</th><th>0300</th></tr>
      <tr><td>icon</td><td>icon</td><td>0%</td><td>0%</td><td>0%</td></tr>
    </table>
    </body></html>
    """
    pct, t = parse_peak_rain(html)
    assert pct == 0
    assert t == ""


def test_parse_peak_rain_breaks_ties_to_earliest():
    html = """
    <html><body>
    <table class="hourlywind">
      <tr><th></th><th></th><th>1000</th><th>1100</th><th>1200</th></tr>
      <tr><td>icon</td><td>icon</td><td>50%</td><td>88%</td><td>88%</td></tr>
    </table>
    </body></html>
    """
    pct, t = parse_peak_rain(html)
    assert pct == 88
    assert t == "11:00"


def test_parse_peak_rain_handles_unlabeled_midnight_column():
    # Mirror the real meteoblue layout: an empty <td> for midnight followed by
    # labeled hour cells. If midnight has the peak %, the time should still
    # render as "00:00" instead of "".
    html = """
    <html><body>
    <table class="hourlywind">
      <tr><th></th><td></td><td>0100</td><td>0200</td></tr>
      <tr><td>icon</td><td>90%</td><td>20%</td><td>10%</td></tr>
    </table>
    </body></html>
    """
    pct, t = parse_peak_rain(html)
    assert pct == 90
    assert t == "00:00"


def test_extract_returns_full_forecast():
    f = extract(FIXTURE)
    assert isinstance(f, Forecast)
    assert f.today.label == "Today"
    assert f.tomorrow.label == "Tomorrow"
    assert 0 <= f.peak_rain_pct <= 100
