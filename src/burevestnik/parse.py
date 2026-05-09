"""Pure HTML -> typed forecast data.

No I/O, no browser. All inputs are HTML strings; outputs are dataclasses.
"""
import re
from selectolax.parser import HTMLParser

from burevestnik.models import DaySummary, Forecast

_TEMP_RE = re.compile(r"(-?\d+)\s*\xb0C")   # matches "19 °C" — text already normalized via split()/join()
_WIND_RE = re.compile(r"(\d+)\s*kn(?![a-zA-Z])")
_RAIN_RE = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*mm")
_SUN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*h\b")


def parse_day(html: str, selector: str) -> DaySummary:
    """Extract a DaySummary from a #dayN tab's text content.

    With units forced to °C / kn / mm by the scraper's settings clicks, the
    tab text (after whitespace normalisation) looks like:
      "MonToday19 °C14 °C7 kn0-2 mm5 h"   (or with spaces between fields)

    Weekday and label are extracted from the .tab-day-short and .tab-day-long
    child elements because they are sometimes concatenated without a separator
    in the flattened text. Numeric values are extracted with regexes.
    """
    doc = HTMLParser(html)
    el = doc.css_first(selector)
    if el is None:
        raise ValueError(f"no element matching {selector!r}")

    # Weekday ("Mon") and label ("Today" / "Tomorrow") live in dedicated children.
    day_short = el.css_first(".tab-day-short")
    day_long = el.css_first(".tab-day-long")
    if day_short is None or day_long is None:
        raise ValueError(f"missing .tab-day-short/.tab-day-long in {selector!r}")
    weekday = day_short.text(strip=True)
    label = day_long.text(strip=True)

    # Full normalised text for numeric extraction.
    text = " ".join(el.text(strip=True).split())

    temps = _TEMP_RE.findall(text)
    if len(temps) < 2:
        raise ValueError(f"expected two °C values in {text!r}")
    temp_max_c, temp_min_c = int(temps[0]), int(temps[1])

    wind_match = _WIND_RE.search(text)
    if wind_match is None:
        raise ValueError(f"no wind speed in {text!r}")
    wind_kn_max = int(wind_match.group(1))

    rain_match = _RAIN_RE.search(text)
    if rain_match is not None:
        rain_mm_low = float(rain_match.group(1))
        rain_mm_high = float(rain_match.group(2)) if rain_match.group(2) else rain_mm_low
    else:
        # Dry forecast: meteoblue shows a dash instead of a mm range, treated
        # as 0 mm. If peak_rain_pct > 0 in the same Forecast, that's a hint
        # that the page layout changed (mm span vanished while the percent
        # row remained) — the caption will then show "0mm alongside Peak N%".
        rain_mm_low = 0.0
        rain_mm_high = 0.0

    sun_match = _SUN_RE.search(text)
    if sun_match is None:
        raise ValueError(f"no sun hours in {text!r}")
    sun_hours = float(sun_match.group(1))

    return DaySummary(
        label=label,
        weekday=weekday,
        temp_max_c=temp_max_c,
        temp_min_c=temp_min_c,
        wind_kn_max=wind_kn_max,
        rain_mm_low=rain_mm_low,
        rain_mm_high=rain_mm_high,
        sun_hours=sun_hours,
    )


_PCT_RE = re.compile(r"(\d+)\s*%")


def parse_peak_rain(html: str) -> tuple[int, str]:
    """Find the highest rain-probability hour in table.hourlywind.

    Returns (peak_pct, peak_time as 'HH:00'). Tie-breaking: earliest hour.
    Returns (0, "") if no rain forecast at all.
    """
    doc = HTMLParser(html)
    table = doc.css_first("table.hourlywind")
    if table is None:
        raise ValueError("table.hourlywind not found in document")

    rows = table.css("tr")
    if not rows:
        raise ValueError("table.hourlywind has no rows")

    # Header row: hour labels like "0100", "0200", ... possibly "01 00"
    header_cells = rows[0].css("th, td")
    hours: list[str] = []
    for cell in header_cells:
        digits = re.sub(r"\D", "", cell.text(strip=True))
        if len(digits) >= 2 and digits[:2].isdigit():
            hh = int(digits[:2])
            if 0 <= hh <= 23:
                hours.append(f"{hh:02d}:00")
                continue
        hours.append("")

    # Find the row whose data cells are predominantly percentages.
    rain_row = None
    for row in rows[1:]:
        cells = row.css("th, td")
        if not cells:
            continue
        pct_count = sum(1 for c in cells if "%" in c.text())
        if pct_count >= max(1, int(len(cells) * 0.6)):
            rain_row = row
            break

    if rain_row is None:
        raise ValueError("no rain probability row found in table.hourlywind")

    cells = rain_row.css("th, td")
    pcts: list[tuple[int, str]] = []  # (pct, hour_label)
    for idx, cell in enumerate(cells):
        m = _PCT_RE.search(cell.text())
        if m is None:
            continue
        pcts.append((int(m.group(1)), hours[idx] if idx < len(hours) else ""))

    if not pcts:
        return 0, ""

    max_pct = max(p for p, _ in pcts)
    if max_pct == 0:
        return 0, ""

    # Earliest tie-break: first occurrence in document order.
    # If the peak's hour cell is unlabeled (e.g. an empty <td> for the
    # midnight column whose label is implicit), fall back to "00:00".
    for pct, hour in pcts:
        if pct == max_pct:
            return pct, hour or "00:00"
    return 0, ""


def extract(html: str) -> Forecast:
    """Parse today + tomorrow + peak rain from a meteoblue weekly-view HTML."""
    today = parse_day(html, "#day1")
    tomorrow = parse_day(html, "#day2")
    peak_pct, peak_time = parse_peak_rain(html)
    return Forecast(
        today=today,
        tomorrow=tomorrow,
        peak_rain_pct=peak_pct,
        peak_rain_time=peak_time,
    )
