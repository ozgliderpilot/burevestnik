"""Pure HTML -> typed forecast data.

No I/O, no browser. All inputs are HTML strings; outputs are dataclasses.
"""
import re
from selectolax.parser import HTMLParser

from burevestnik.models import DaySummary, Forecast, ForecastDay, ForecastDayKind

_TEMP_RE = re.compile(r"(-?\d+)\s*\xb0C")   # matches "19 °C" — text already normalized via split()/join()
_WIND_RE = re.compile(r"(\d+)\s*kn(?![a-zA-Z])")
_WIND_INT_RE = re.compile(r"\d+")
_RAIN_RE = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*mm")
_SUN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*h\b")


def parse_day(html: str, selector: str) -> DaySummary:
    """Extract a DaySummary from a #dayN tab's text content.

    With units forced to °C / kn / mm by the scraper's settings clicks, the
    tab text (after whitespace normalisation) looks like:
      "MonToday19 °C14 °C7 kn0-2 mm5 h"   (or with spaces between fields)

    Weekday and label are extracted from the .tab-day-short and .tab-day-long
    child elements because they are sometimes concatenated without a separator
    in the flattened text. The four numeric fields are likewise read from their
    dedicated children (.tab-temp-max/.tab-temp-min, div.wind, div.tab-precip,
    div.tab-sun) rather than the flattened tab text: on high-wind days the wind
    value loses its inline "kn" unit and becomes a range ("13-34") that runs
    straight into the rain field in the flattened text ("13-345-10 mm"), which
    defeats unit-anchored regexes — so each field is isolated to its own
    element, with a flattened-text regex fallback for markup that lacks the
    dedicated divs. See _parse_temps_c / _parse_wind_kn_max / _parse_rain_mm /
    _parse_sun_hours.
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

    temp_max_c, temp_min_c = _parse_temps_c(el, text)
    wind_kn_max = _parse_wind_kn_max(el, text)
    rain_mm_low, rain_mm_high = _parse_rain_mm(el, text)
    sun_hours = _parse_sun_hours(el, text)

    # Day-variant weather pictogram. The `night` sibling is intentionally not
    # consulted — captions always describe a whole day.
    pic = el.css_first(".weather-pictogram-wrapper.day img.weather-pictogram")
    condition = pic.attributes.get("alt") if pic is not None else None

    return DaySummary(
        label=label,
        weekday=weekday,
        temp_max_c=temp_max_c,
        temp_min_c=temp_min_c,
        wind_kn_max=wind_kn_max,
        rain_mm_low=rain_mm_low,
        rain_mm_high=rain_mm_high,
        sun_hours=sun_hours,
        condition=condition,
    )


def _parse_temps_c(el, text: str) -> tuple[int, int]:
    """Resolve (max, min) day-tab temperature in °C.

    Reads the dedicated div.tab-temp-max / div.tab-temp-min children ("14 °C")
    rather than relying on the order of °C tokens in the flattened tab text.
    Falls back to the first two °C values in the flattened text when those divs
    are absent (e.g. synthetic test markup). See parse_day's docstring for why
    every numeric field is isolated to its own element.
    """
    max_el = el.css_first("div.tab-temp-max")
    min_el = el.css_first("div.tab-temp-min")
    if max_el is not None and min_el is not None:
        max_m = _TEMP_RE.search(max_el.text())
        min_m = _TEMP_RE.search(min_el.text())
        if max_m is not None and min_m is not None:
            return int(max_m.group(1)), int(min_m.group(1))

    temps = _TEMP_RE.findall(text)
    if len(temps) < 2:
        raise ValueError(f"expected two °C values in {text!r}")
    return int(temps[0]), int(temps[1])


def _parse_wind_kn_max(el, text: str) -> int:
    """Resolve the day-tab wind speed in knots, tolerating high-wind markup.

    Normal days render the wind as a single value with an inline unit
    ("8 kn") inside div.wind. High-wind days render a "speed-gust" range
    without the unit ("13-34" = 13 kn wind, 34 kn gust) and move the unit into
    the div's title attribute (title="Wind speed (kn)") plus a warning
    background colour. We take the first value — the wind speed — which is the
    single value on normal days and the lower (left) bound of the range on
    high-wind days (gusts are surfaced separately via gust_kn_max from the
    hourly table). Reading the dedicated div.wind mirrors how
    weekday/label/condition are read from dedicated children rather than the
    flattened tab text. Falls back to the kn-anchored regex on the flattened
    text when div.wind is absent (e.g. synthetic test markup).
    """
    wind_el = el.css_first("div.wind")
    if wind_el is not None:
        nums = _WIND_INT_RE.findall(wind_el.text())
        if nums:
            return int(nums[0])

    wind_match = _WIND_RE.search(text)
    if wind_match is None:
        raise ValueError(f"no wind speed in {text!r}")
    return int(wind_match.group(1))


def _parse_rain_mm(el, text: str) -> tuple[float, float]:
    """Resolve the day-tab precipitation (low, high) in mm.

    Reads the dedicated div.tab-precip ("5-10 mm", "0-2 mm", or "-" when dry)
    rather than the flattened tab text. This matters on high-wind days: the
    wind range loses its inline unit ("13-34") and runs straight into the rain
    field in the flattened text ("13-345-10 mm"), which would make _RAIN_RE
    misread the low bound as 345. Falls back to the flattened text when
    div.tab-precip is absent (e.g. synthetic test markup). A dash (no match)
    is a dry forecast → (0.0, 0.0).
    """
    precip_el = el.css_first("div.tab-precip")
    source = precip_el.text() if precip_el is not None else text
    m = _RAIN_RE.search(source)
    if m is None:
        return 0.0, 0.0
    low = float(m.group(1))
    high = float(m.group(2)) if m.group(2) else low
    return low, high


def _parse_sun_hours(el, text: str) -> float:
    """Resolve the day-tab sunshine hours.

    Reads the dedicated div.tab-sun child ("4 h") rather than the flattened tab
    text, falling back to the flattened text when that div is absent (e.g.
    synthetic test markup). See parse_day's docstring for why every numeric
    field is isolated to its own element. Raises ValueError when no parseable
    "N h" value is found, preserving the original loud-failure behaviour.
    """
    sun_el = el.css_first("div.tab-sun")
    source = sun_el.text() if sun_el is not None else text
    m = _SUN_RE.search(source)
    if m is None:
        raise ValueError(f"no sun hours in {text!r}")
    return float(m.group(1))


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

    header_row = table.css_first("tr.times")
    if header_row is None:
        raise ValueError("tr.times header row not found in table.hourlywind")
    hours = _hour_labels(header_row)

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
    # meteoblue reports precip at 0.1mm precision, so anything below that is no rain.
    if max_mm < 0.05:
        return 0.0, ""

    # Earliest tie-break (document order). Midnight fallback on empty label.
    peak_hour = next(hour for mm, hour in values if mm == max_mm)
    return max_mm, peak_hour or "00:00"


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


_HHMM_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")


def parse_sun_times(html: str) -> tuple[str, str] | tuple[None, None]:
    """Extract (sunrise, sunset) as "HH:MM" strings from the page.

    meteoblue renders these as `<div title="Sunrise">… 07:08</div>` and
    `<div title="Sunset">… 17:23</div>`, duplicated across no-mobile /
    no-desktop variants. We take the first occurrence of each. The times
    already reflect whichever day the page was fetched for (today, or
    tomorrow via ?day=2), so no date math is needed downstream.

    Returns (None, None) when either div is missing or its text contains
    no parseable HH:MM — the caption treats the sun line as optional.
    """
    doc = HTMLParser(html)
    rise_el = doc.css_first('div[title="Sunrise"]')
    set_el = doc.css_first('div[title="Sunset"]')
    if rise_el is None or set_el is None:
        return None, None
    rise_m = _HHMM_RE.search(rise_el.text())
    set_m = _HHMM_RE.search(set_el.text())
    if rise_m is None or set_m is None:
        return None, None
    return rise_m.group(1), set_m.group(1)


def parse_days(html: str, count: int = 5) -> list[DaySummary]:
    """Extract the first `count` day-tab summaries (#day1 … #day{count}).

    Reuses parse_day per tab. #day1 is always today, so the list is the next
    `count` days in order from whatever day the page was fetched on. Raises
    ValueError (via parse_day) if any expected tab is missing.
    """
    return [parse_day(html, f"#day{n}") for n in range(1, count + 1)]


def extract(html: str, *, day: ForecastDay) -> Forecast:
    """Parse the displayed forecast from a meteoblue weekly-view HTML.

    Primary tab is `#day{day.page_index}`. When Forecast day is Today,
    `#day{page_index + 1}` is the next-day preview; when it is Tomorrow
    the preview is omitted (`next_day_preview=None`).

    The hourly metrics (peak rain mm, felt temp high/low) are read from
    table.hourlywind, which reflects whichever day the page was fetched
    for (?day=2 swaps it to tomorrow at the runtime/scrape layer).
    """
    primary = parse_day(html, f"#day{day.page_index}")
    next_day: DaySummary | None
    if day.kind is ForecastDayKind.TOMORROW:
        next_day = None
    else:
        next_day = parse_day(html, f"#day{day.page_index + 1}")
    peak_mm, peak_time = parse_peak_rain_mm(html)
    felt_hi, felt_lo = parse_temp_felt(html)
    uv = parse_uv(html)
    wind_lo, wind_hi = parse_wind_range(html)
    gust = parse_peak_gust_kn(html)
    sunrise, sunset = parse_sun_times(html)
    return Forecast(
        day=day,
        primary=primary,
        next_day_preview=next_day,
        peak_rain_mm=peak_mm,
        peak_rain_time=peak_time,
        uv_index=uv,
        temp_felt_max_c=felt_hi,
        temp_felt_min_c=felt_lo,
        wind_kn_low=wind_lo,
        wind_kn_high=wind_hi,
        gust_kn_max=gust,
        sunrise=sunrise,
        sunset=sunset,
    )
