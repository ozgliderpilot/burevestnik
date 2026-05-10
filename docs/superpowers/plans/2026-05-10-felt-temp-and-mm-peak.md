# Felt-temperature headline + mm-based rain peak — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the caption High/Low to the *felt* temperature (with a 🤚🌡 icon) and change the rain peak from probability (%) to amount (mm), with the rain line always emitted (including a `☔ No rain` form on dry days).

**Architecture:** Two new pure parser functions read additional rows from the existing `table.hourlywind`. The `Forecast` model gains felt-temp fields and swaps `peak_rain_pct: int` for `peak_rain_mm: float`. The caption renderer uses the new fields. The schema swap is a single atomic commit (Task 3) because both `parse.extract()` and the caption test factory depend on the field name.

**Tech Stack:** Python 3.13, selectolax (HTML parsing), pytest, uv, dataclasses (frozen).

**Spec:** `docs/superpowers/specs/2026-05-10-felt-temp-and-mm-peak-design.md`

---

## Reference: project conventions

- Tests are run with `uv run pytest`. A single test: `uv run pytest tests/test_parse.py::test_name -v`.
- Parser tests live in `tests/test_parse.py` and use `tests/fixtures/meteoblue.html` (no live network).
- All parsing functions raise `ValueError` on missing/unexpected layout (see existing `parse_day`, `parse_uv`).
- `parse.py`, `caption.py`, and `models.py` are pure; only `scrape.py` does I/O.
- Frozen dataclasses — never mutate; reconstruct.

---

## File structure

| File | Change |
| --- | --- |
| `src/burevestnik/parse.py` | Add `parse_temp_felt`, add `parse_peak_rain_mm`, drop `parse_peak_rain`, update `extract()`. |
| `src/burevestnik/models.py` | `Forecast`: drop `peak_rain_pct: int`, add `peak_rain_mm: float`, `temp_felt_max_c: int`, `temp_felt_min_c: int`. |
| `src/burevestnik/caption.py` | New thermometer line (felt + 🤚🌡, no `<b>`); always-emit rain line; new `_format_peak_mm` helper. |
| `tests/test_parse.py` | Drop probability-peak tests; add tests for both new parsers; update `extract` assertions. |
| `tests/test_models.py` | Replace `peak_rain_pct=88` with `peak_rain_mm=1.5`; add felt-temp fields to constructions. |
| `tests/test_caption.py` | Update `_make_forecast` factory; update assertions; new `No rain`, peak-mm formatting tests. |
| `CLAUDE.md` | Replace the "0mm alongside Peak N%" diagnostic-signal note. |

---

## Task 1: Add `parse_temp_felt` to parse.py

**Files:**
- Modify: `src/burevestnik/parse.py` (append a new function after `parse_uv`)
- Test: `tests/test_parse.py` (append new tests)

The function reads `tr.temperature-felt` inside `table.hourlywind` and returns `(max_c, min_c)` as a tuple of ints. Each `<td>` in that row contains text like `"10°"` (sometimes `"-3°"`); the leading integer is the felt temperature. The header `<th>` (which has no numeric text) is ignored by selecting only `td` cells.

**Fixture context:** the captured `tests/fixtures/meteoblue.html` has 24 felt-temp cells with values: 10, 10, 10, 10, 10, 10, 10, 10, 11, 12, 12, 12, 13, 13, 13, 12, 12, 12, 12, 12, 12, 11, 11, 11. So `(max, min) == (13, 10)` for that fixture.

- [ ] **Step 1.1: Write the failing tests**

Add to the bottom of `tests/test_parse.py`:

```python
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
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parse.py -k parse_temp_felt -v`
Expected: 4 errors / failures with `ImportError: cannot import name 'parse_temp_felt' from 'burevestnik.parse'`.

- [ ] **Step 1.3: Implement `parse_temp_felt` in `src/burevestnik/parse.py`**

Add this function near the bottom of `src/burevestnik/parse.py`, before `def extract(...)`:

```python
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
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_parse.py -k parse_temp_felt -v`
Expected: 4 passed.

- [ ] **Step 1.5: Run the full suite to confirm no regressions**

Run: `uv run pytest -v`
Expected: all existing tests still pass; 4 new tests pass.

- [ ] **Step 1.6: Commit**

```bash
git add src/burevestnik/parse.py tests/test_parse.py
git commit -m "feat(parse): add parse_temp_felt for hourly felt-temperature row"
```

---

## Task 2: Add `parse_peak_rain_mm` to parse.py

**Files:**
- Modify: `src/burevestnik/parse.py` (append after `parse_temp_felt`)
- Test: `tests/test_parse.py` (append new tests)

The function reads `tr.precip` inside `table.hourlywind` and returns `(max_mm, "HH:00")`. Each `<td>` contains an inner `<span>` that is empty when there's no rain (text `""`) and contains an mm value as a float-stringy number like `"0.5"` or `"2"` when there is rain. Earliest-hour tie-break, mirroring `parse_peak_rain`'s contract. Returns `(0.0, "")` when every cell is empty/zero. Raises `ValueError` if `tr.precip` is missing.

The hour-label extraction reuses the same approach as `parse_peak_rain` (extract digits from each header cell, take first two as `HH`). The same midnight-fallback applies: if the peak's hour cell is unlabeled, return `"00:00"`.

**Fixture context:** every cell in the fixture's `tr.precip` is `<td><span></span></td>` (no rain mm), so the fixture must yield `(0.0, "")`.

- [ ] **Step 2.1: Write the failing tests**

Add to the bottom of `tests/test_parse.py`:

```python
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
    # Mirrors parse_peak_rain: an empty <td> for the midnight column whose
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
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parse.py -k parse_peak_rain_mm -v`
Expected: 6 errors / failures with `ImportError: cannot import name 'parse_peak_rain_mm' from 'burevestnik.parse'`.

- [ ] **Step 2.3: Implement `parse_peak_rain_mm` in `src/burevestnik/parse.py`**

Add this function near the bottom of `src/burevestnik/parse.py`, after `parse_temp_felt`, before `def extract(...)`:

```python
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
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_parse.py -k parse_peak_rain_mm -v`
Expected: 6 passed.

- [ ] **Step 2.5: Run the full suite**

Run: `uv run pytest -v`
Expected: all existing tests still pass; new ones pass.

- [ ] **Step 2.6: Commit**

```bash
git add src/burevestnik/parse.py tests/test_parse.py
git commit -m "feat(parse): add parse_peak_rain_mm for hourly precipitation amount"
```

---

## Task 3: Atomic flip — swap Forecast schema, rewire extract() and caption, update all dependent tests

**Files:**
- Modify: `src/burevestnik/models.py`
- Modify: `src/burevestnik/parse.py` (drop `parse_peak_rain`, update `extract`)
- Modify: `src/burevestnik/caption.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_parse.py` (drop `parse_peak_rain` tests, update `extract` tests)
- Modify: `tests/test_caption.py`

This task is committed in one go because the field rename (`peak_rain_pct` → `peak_rain_mm`) and type change (`int` → `float`) cannot be split across commits without leaving the suite red.

### Step 3.1: Update the model

- [ ] **Edit `src/burevestnik/models.py`** — replace the `Forecast` dataclass with:

```python
@dataclass(frozen=True)
class Forecast:
    today: DaySummary
    tomorrow: DaySummary | None  # None when running in tomorrow-mode (post-16:00)
    peak_rain_mm: float          # max hourly mm across the displayed day's precip row; 0.0 if dry
    peak_rain_time: str          # "HH:00" — the slot where peak hit; "" if no rain
    uv_index: int                # primary day's UV index (from page-level uv-index block)
    temp_felt_max_c: int         # max felt °C across the displayed day's temperature-felt row
    temp_felt_min_c: int         # min felt °C across the displayed day's temperature-felt row
```

(Leave `DaySummary` untouched.)

### Step 3.2: Update model tests

- [ ] **Edit `tests/test_models.py`** — replace `test_forecast_constructs` and `test_forecast_has_uv_index`:

```python
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
    )
    assert f.peak_rain_mm == 1.5
    assert f.temp_felt_max_c == 18
    assert f.temp_felt_min_c == 10


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
    )
    assert f.uv_index == 4
```

(Leave `test_day_summary_constructs` and `test_dataclasses_are_frozen` untouched.)

### Step 3.3: Update `parse.py` — drop `parse_peak_rain`, rewire `extract()`

- [ ] **Delete the entire `parse_peak_rain` function** from `src/burevestnik/parse.py` (the old probability-based one — everything from `def parse_peak_rain(html: str) -> tuple[int, str]:` through its `return 0, ""`). The `_PCT_RE = re.compile(r"(\d+)\s*%")` line is no longer used by anything in `parse.py`; delete it as well. The `_UV_RE` line stays (used by `parse_uv`).

- [ ] **Replace the body of `extract()`** in `src/burevestnik/parse.py` with:

```python
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
    return Forecast(
        today=primary,
        tomorrow=next_day,
        peak_rain_mm=peak_mm,
        peak_rain_time=peak_time,
        uv_index=uv,
        temp_felt_max_c=felt_hi,
        temp_felt_min_c=felt_lo,
    )
```

### Step 3.4: Update `tests/test_parse.py`

- [ ] **Delete these obsolete tests** (they test the removed `parse_peak_rain`):
  - `test_parse_peak_rain_returns_int_and_hh_mm`
  - `test_parse_peak_rain_no_table_raises`
  - `test_parse_peak_rain_zero_percent_returns_empty_time`
  - `test_parse_peak_rain_breaks_ties_to_earliest`
  - `test_parse_peak_rain_handles_unlabeled_midnight_column`

- [ ] **Update the import line** at the top of `tests/test_parse.py` from:
```python
from burevestnik.parse import parse_day, parse_peak_rain, extract
```
to:
```python
from burevestnik.parse import parse_day, extract
```

- [ ] **Replace `test_extract_returns_full_forecast`** with:

```python
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
```

- [ ] **Replace `test_extract_for_tomorrow_sets_tomorrow_field_to_none`** with:

```python
def test_extract_for_tomorrow_sets_tomorrow_field_to_none():
    f = extract(FIXTURE, for_tomorrow=True)
    assert f.tomorrow is None
    # Sanity: peak rain still resolves (parser ignores the flag for hourly
    # — the page swap from ?day=2 is the runtime mechanism).
    assert f.peak_rain_mm >= 0.0
```

(Leave the rest of `tests/test_parse.py` untouched, including the `test_parse_peak_rain_mm_*` and `test_parse_temp_felt_*` tests added in Tasks 1–2.)

### Step 3.5: Update `caption.py`

- [ ] **Edit `src/burevestnik/caption.py`** — add a new helper near `_format_rain_range`:

```python
def _format_peak_mm(mm: float) -> str:
    """Format hourly mm with one decimal, stripping a trailing zero.

    0.5 -> "0.5mm"; 1.5 -> "1.5mm"; 12.0 -> "12mm".
    """
    return f"{round(mm, 1):g}mm"
```

- [ ] **Replace the thermometer line** (currently `lines.append(f"🌡 High <b>{round(today.temp_max_c)}°</b> / Low {round(today.temp_min_c)}°")`) with:

```python
lines.append(
    f"🤚🌡 High {round(forecast.temp_felt_max_c)}° / Low {round(forecast.temp_felt_min_c)}°"
)
```

- [ ] **Replace the rain block** (currently the `if forecast.peak_rain_pct > 0: …` block) with:

```python
if today.rain_mm_high == 0:
    lines.append("☔ No rain")
else:
    rain_str = _format_rain_range(today.rain_mm_low, today.rain_mm_high)
    rain_line = f"☔ Rain {rain_str}"
    if forecast.peak_rain_mm > 0:
        rain_line += (
            f" · Peak <b>{_format_peak_mm(forecast.peak_rain_mm)}</b> "
            f"at {forecast.peak_rain_time}"
        )
    lines.append(rain_line)
```

(Leave the wind, sun, UV, tomorrow-preview, and "Updated" lines untouched.)

### Step 3.6: Update `tests/test_caption.py`

- [ ] **Replace the `_make_forecast` factory** at the top of `tests/test_caption.py` with:

```python
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
```

- [ ] **Replace `test_render_full_template`** with:

```python
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
    assert "AEST" in out
    assert f'<a href="{_SOURCE_URL}">meteoblue</a>' in out
```

- [ ] **Replace `test_collapses_equal_rain_range`** with (rebuilding `f` no longer needs the keyword-args dance because the factory now takes `rain_mm_low/high`):

```python
def test_collapses_equal_rain_range():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(rain_mm_low=5.0, rain_mm_high=5.0, peak_mm=0.5, peak_time="12:00")
    out = render(f, now, _SOURCE_URL)
    assert "5mm" in out
    assert "5–5mm" not in out
    assert "5-5mm" not in out
```

- [ ] **Delete `test_drops_rain_line_when_zero_peak`** — it asserts the old "drop the rain line entirely" behavior, which no longer exists. **Replace it** with two new tests covering the new always-emit behavior:

```python
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
```

- [ ] **Add formatting tests** for `_format_peak_mm`:

```python
def test_render_peak_mm_formats_one_decimal():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(peak_mm=1.5, peak_time="14:00"), now, _SOURCE_URL)
    assert "Peak <b>1.5mm</b> at 14:00" in out


def test_render_peak_mm_strips_trailing_zero():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(peak_mm=12.0, peak_time="14:00"), now, _SOURCE_URL)
    assert "Peak <b>12mm</b> at 14:00" in out
    assert "12.0mm" not in out
```

- [ ] **Audit other tests that reference `peak_pct` or `<b>21°</b>`:**

The following tests use `_make_forecast(...)` with the now-removed `peak_pct=` parameter. Update them to use `peak_mm=` (the actual value doesn't matter for these tests, default `1.5` is fine, but keep parametrized calls intact):

  - `test_render_tomorrow_mode_header_contains_tomorrow_prefix_and_shifted_date` — currently `_make_forecast(tomorrow=None)`, no kwarg change needed.
  - `test_render_tomorrow_mode_omits_preview_line` — same.
  - `test_render_tomorrow_mode_keeps_run_time_in_updated_line` — same.
  - `test_render_tomorrow_mode_uses_shifted_date_for_sun_lookup` — same.
  - `test_render_includes_uv_line_today_mode` — `_make_forecast(uv_index=2)`, no change.
  - `test_render_includes_uv_line_tomorrow_mode` — `_make_forecast(tomorrow=None, uv_index=7)`, no change.
  - `test_render_uv_line_appears_after_sun_line` — `_make_forecast(uv_index=4)`, no change.
  - `test_render_uv_line_appears_after_wind_when_sun_unavailable` — `_make_forecast(uv_index=4)`, no change.
  - `test_render_tomorrow_preview_line_does_not_include_uv` — `_make_forecast(uv_index=4)`, no change.
  - `test_render_uv_line_present_at_uv_zero` — `_make_forecast(uv_index=0)`, no change.

The only test that specifically uses `peak_pct=` was `test_collapses_equal_rain_range` (already replaced above) and `test_drops_rain_line_when_zero_peak` (deleted above). No other tests need a kwarg edit.

### Step 3.7: Run the suite

- [ ] **Run the full suite:**

Run: `uv run pytest -v`
Expected: all tests pass — both the existing untouched ones and the rewritten ones from this task.

If anything fails, the most likely causes are:
- A leftover reference to `peak_rain_pct` somewhere (run `git grep peak_rain_pct` to find it).
- A leftover reference to `parse_peak_rain` (no `_mm` suffix) — `git grep "parse_peak_rain\b"`.
- A typo in field order on the `Forecast(...)` constructor (kwargs are required; positional won't work — check the test factory).

### Step 3.8: Commit

- [ ] **Commit:**

```bash
git add src/burevestnik/models.py src/burevestnik/parse.py src/burevestnik/caption.py \
        tests/test_models.py tests/test_parse.py tests/test_caption.py
git commit -m "$(cat <<'EOF'
feat: switch caption to felt-temp headline and mm-based rain peak

Forecast: drop peak_rain_pct (int %), add peak_rain_mm (float mm) and
felt-temp high/low. extract() now reads tr.precip and tr.temperature-felt
from table.hourlywind; the old probability-based parse_peak_rain is gone.

Caption: thermometer line uses 🤚🌡 + felt high/low (no bold). Rain line
is always emitted — "☔ No rain" when the daily mm range is 0, otherwise
the range, with "· Peak <b>X.Xmm</b> at HH:00" appended only when the
hourly peak mm is non-zero.
EOF
)"
```

---

## Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the project-root version, not the spec doc)

The architecture section currently has a paragraph ending in:

> If meteoblue ever changes the layout enough that the rain-mm span vanishes but the percent row remains, the caption will surface this as `0mm alongside Peak N%` — that's the diagnostic signal, not a bug.

That diagnostic signal is obsolete now (we no longer use the percent row). Replace the whole `parse.parse_peak_rain` paragraph with one describing the new parsers.

- [ ] **Step 4.1: Edit `CLAUDE.md`**

Find the paragraph that begins with `parse.parse_peak_rain finds the row in table.hourlywind …` and replace the entire paragraph with:

```markdown
`parse.parse_peak_rain_mm` reads the row of hourly mm values from `table.hourlywind` (`tr.precip`) and returns the highest value with the earliest tie-break; `parse.parse_temp_felt` reads `tr.temperature-felt` from the same table and returns `(max, min)`. Both reflect whichever day the page was fetched for (`?day=2` swaps the table to tomorrow at the scrape layer), so they need no `for_tomorrow` flag.
```

- [ ] **Step 4.2: Verify the change**

Run: `git -C C:/Users/vital/git/telegram/burevestnik diff CLAUDE.md`
Confirm: only the targeted paragraph is replaced; no other markdown changes.

- [ ] **Step 4.3: Run the suite once more for sanity**

Run: `uv run pytest -v`
Expected: all tests pass (no code changed).

- [ ] **Step 4.4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE): describe new mm-peak and felt-temp parsers"
```

---

## Done

After Task 4, the work matches the spec. Run one final end-to-end sanity check:

```bash
uv run pytest -v
git -C C:/Users/vital/git/telegram/burevestnik log --oneline -10
```

You should see four new commits on top of the spec commits, the test suite green, and no remaining references to `peak_rain_pct`, `parse_peak_rain` (without `_mm`), or the old "0mm alongside Peak N%" note.
