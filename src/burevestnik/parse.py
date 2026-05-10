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
        # Dry forecast: meteoblue shows a dash instead of a mm range, treated as 0 mm.
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


_UV_RE = re.compile(r"UV\s*(\d+)")


def parse_uv(html: str) -> int:
    """Extract the page-level UV index integer.

    The uv-index block lives in a model-info / celestial-bodies section, not
    inside any #dayN tab. It reflects whichever day the page is displaying
    (today on the default fetch, tomorrow when the page is fetched with
    ?day=2). The block is duplicated in the markup (no-mobile and no-desktop
    variants); both carry identical content, so the first match is fine.
    """
    doc = HTMLParser(html)
    el = doc.css_first("div.uv-index")
    if el is None:
        raise ValueError("uv-index element not found in document")
    text = " ".join(el.text(strip=True).split())
    m = _UV_RE.search(text)
    if m is None:
        raise ValueError(f"no UV value in uv-index text {text!r}")
    return int(m.group(1))


_TEMP_CELL_RE = re.compile(r"(-?\d+)\s*°")


def parse_temp_felt(html: str) -> tuple[int, int]:
    """Extract (max, min) felt temperature from tr.temperature-felt.

    The temperature-felt row lives inside table.hourlywind and carries 24
    hourly °C cells like "10°", "13°", "-3°". The leading <th> has no
    numeric content and is excluded by selecting only <td> cells.

    Raises ValueError if the row is missing or contains no numeric cells.
    """
    doc = HTMLParser(html)
    row = doc.css_first("tr.temperature-felt")
    if row is None:
        raise ValueError("tr.temperature-felt row not found in document")

    values: list[int] = []
    for cell in row.css("td"):
        m = _TEMP_CELL_RE.search(cell.text())
        if m is not None:
            values.append(int(m.group(1)))

    if not values:
        raise ValueError("tr.temperature-felt has no numeric cells")

    return max(values), min(values)


_PRECIP_MM_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _hour_labels(header_row) -> list[str]:
    """Extract HH:00 labels from a table.hourlywind header row.

    Each header cell text is reduced to digits; the first two digits are
    interpreted as hours. Cells without parseable hours map to "" so the
    list stays index-aligned with the data row.
    """
    hours: list[str] = []
    for cell in header_row.css("th, td"):
        digits = re.sub(r"\D", "", cell.text(strip=True))
        if len(digits) >= 2 and digits[:2].isdigit():
            hh = int(digits[:2])
            if 0 <= hh <= 23:
                hours.append(f"{hh:02d}:00")
                continue
        hours.append("")
    return hours


def parse_peak_rain_mm(html: str) -> tuple[float, str]:
    """Find the peak hourly rainfall in mm from tr.precip.

    Returns (max_mm, "HH:00") with earliest-hour tie-break. Returns
    (0.0, "") when every cell is empty or zero.

    Raises ValueError when tr.precip itself is missing.
    """
    doc = HTMLParser(html)
    table = doc.css_first("table.hourlywind")
    if table is None:
        raise ValueError("table.hourlywind not found in document")

    rain_row = table.css_first("tr.precip")
    if rain_row is None:
        raise ValueError("tr.precip row not found in table.hourlywind")

    rows = table.css("tr")
    hours = _hour_labels(rows[0]) if rows else []

    cells = rain_row.css("th, td")
    values: list[tuple[float, str]] = []  # (mm, hour_label)
    for idx, cell in enumerate(cells):
        m = _PRECIP_MM_RE.search(cell.text())
        if m is None:
            continue
        values.append((float(m.group(1)), hours[idx] if idx < len(hours) else ""))

    if not values:
        return 0.0, ""

    max_mm = max(mm for mm, _ in values)
    if max_mm == 0.0:
        return 0.0, ""

    # Earliest tie-break (document order). Midnight fallback on empty label.
    for mm, hour in values:
        if mm == max_mm:
            return mm, hour or "00:00"
    return 0.0, ""


_INT_CELL_RE = re.compile(r"-?\d+")


def parse_wind_range(html: str) -> tuple[int, int]:
    """Extract (min, max) hourly wind speed in knots from tr.windspeed.

    The windspeed row inside table.hourlywind carries 24 hourly cells, each
    a bare integer kn value (e.g. "7"). The leading <th> has no numeric
    content and is excluded by selecting only <td> cells.

    Raises ValueError if the row is missing or has no numeric cells.
    """
    doc = HTMLParser(html)
    row = doc.css_first("tr.windspeed")
    if row is None:
        raise ValueError("tr.windspeed row not found in document")

    values: list[int] = []
    for cell in row.css("td"):
        m = _INT_CELL_RE.search(cell.text())
        if m is not None:
            values.append(int(m.group(0)))

    if not values:
        raise ValueError("tr.windspeed has no numeric cells")

    return min(values), max(values)


def parse_peak_gust_kn(html: str) -> int:
    """Extract the peak hourly wind gust in knots from tr.windgust.

    Mirrors parse_wind_range but only returns the max — gust timing is
    typically clustered around the wind peak and not separately rendered.

    Raises ValueError if the row is missing or has no numeric cells.
    """
    doc = HTMLParser(html)
    row = doc.css_first("tr.windgust")
    if row is None:
        raise ValueError("tr.windgust row not found in document")

    values: list[int] = []
    for cell in row.css("td"):
        m = _INT_CELL_RE.search(cell.text())
        if m is not None:
            values.append(int(m.group(0)))

    if not values:
        raise ValueError("tr.windgust has no numeric cells")

    return max(values)


def extract(html: str, *, for_tomorrow: bool = False) -> Forecast:
    """Parse the displayed forecast from a meteoblue weekly-view HTML.

    today-mode (default): #day1 → primary, #day2 → next-day preview.
    tomorrow-mode: #day2 → primary, no next-day preview (Forecast.tomorrow=None).

    The hourly metrics (peak rain mm, felt temp high/low) are read from
    table.hourlywind, which reflects whichever day the page was fetched
    for (?day=2 swaps it to tomorrow at the runtime/scrape layer).
    """
    if for_tomorrow:
        primary = parse_day(html, "#day2")
        next_day: DaySummary | None = None
    else:
        primary = parse_day(html, "#day1")
        next_day = parse_day(html, "#day2")
    peak_mm, peak_time = parse_peak_rain_mm(html)
    felt_hi, felt_lo = parse_temp_felt(html)
    uv = parse_uv(html)
    wind_lo, wind_hi = parse_wind_range(html)
    gust = parse_peak_gust_kn(html)
    return Forecast(
        today=primary,
        tomorrow=next_day,
        peak_rain_mm=peak_mm,
        peak_rain_time=peak_time,
        uv_index=uv,
        temp_felt_max_c=felt_hi,
        temp_felt_min_c=felt_lo,
        wind_kn_low=wind_lo,
        wind_kn_high=wind_hi,
        gust_kn_max=gust,
    )
