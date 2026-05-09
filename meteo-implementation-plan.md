# Burevestnik Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Telegram bot that scrapes meteoblue's North Melbourne forecast 5x daily and posts a screenshot of the 1-hourly weather table plus a rich text caption to a private Telegram channel, deployed on GitHub Actions cron.

**Architecture:** Five-module pipeline: `scrape.py` (Playwright I/O) → `parse.py` (pure HTML→dataclass) → `caption.py` (pure dataclass→string + astral) → `telegram.py` (httpx POST) → `main.py` (orchestrator + DST gate). Workflow runs every UTC hour; `main.py` gates on Melbourne local hour ∈ {6, 9, 12, 15, 18} for DST-safe scheduling.

**Tech Stack:** Python 3.12 · uv · Playwright (Chromium) · selectolax · httpx · astral · pytest · GitHub Actions

**Spec:** see `meteo-plan.md` in the repo root for full design rationale.

---

## File Structure

Files this plan creates (in order of creation):

| Path | Purpose | Created in |
|---|---|---|
| `pyproject.toml` | uv project + deps | Task 1 |
| `.gitignore` | exclusions | Task 1 |
| `src/burevestnik/__init__.py` | package marker | Task 1 |
| `tests/__init__.py` | test package marker | Task 1 |
| `scripts/capture_fixture.py` | one-shot HTML fixture capture | Task 2 |
| `tests/fixtures/meteoblue.html` | captured page HTML for parse tests | Task 2 |
| `src/burevestnik/models.py` | `DaySummary`, `Forecast` dataclasses | Task 3 |
| `src/burevestnik/parse.py` | pure HTML parsing | Tasks 4-6 |
| `tests/test_parse.py` | parse.py tests | Tasks 4-6 |
| `src/burevestnik/caption.py` | pure caption rendering | Tasks 7-8 |
| `tests/test_caption.py` | caption.py tests | Tasks 7-8 |
| `src/burevestnik/scrape.py` | Playwright wrapper | Task 9 |
| `src/burevestnik/telegram.py` | Telegram API wrapper | Task 10 |
| `src/burevestnik/main.py` | orchestrator + DST gate | Task 11 |
| `.github/workflows/post.yml` | cron deployment | Task 12 |
| `README.md` | bot/channel setup instructions | Task 13 |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/burevestnik/__init__.py`, `tests/__init__.py`, `tests/fixtures/.gitkeep`, `scripts/.gitkeep`

- [ ] **Step 1: Initialize git repository**

```powershell
git init
git config core.autocrlf input
```

- [ ] **Step 2: Create `pyproject.toml`**

Path: `pyproject.toml`

```toml
[project]
name = "burevestnik"
version = "0.1.0"
description = "Telegram bot posting meteoblue North Melbourne forecast"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.40",
    "httpx>=0.25",
    "astral>=3.2",
    "selectolax>=0.3.20",
]

[project.optional-dependencies]
dev = ["pytest>=7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/burevestnik"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
pythonpath = ["src"]
```

- [ ] **Step 3: Create `.gitignore`**

Path: `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/
.env

# uv
.uv-cache/

# Playwright artifacts
.playwright-mcp/
test-results/
playwright-report/

# OS
.DS_Store
Thumbs.db

# Local screenshots from the brainstorming session (not part of source)
meteoblue_weather.jpeg
meteoblue_table.jpeg
meteoblue_table_1h.jpeg
```

- [ ] **Step 4: Create directory structure**

```powershell
mkdir src\burevestnik, tests\fixtures, scripts, .github\workflows
ni src\burevestnik\__init__.py -ItemType File
ni tests\__init__.py -ItemType File
ni tests\fixtures\.gitkeep -ItemType File
ni scripts\.gitkeep -ItemType File
```

- [ ] **Step 5: Sync dependencies**

```powershell
uv sync --extra dev
```

Expected: creates `.venv/` and `uv.lock`. No errors.

- [ ] **Step 6: Install Playwright browser**

```powershell
uv run playwright install chromium
```

Expected: downloads Chromium (~150MB on first run).

- [ ] **Step 7: Verify pytest runs (no tests yet, just sanity check)**

```powershell
uv run pytest
```

Expected: `no tests ran` exit code 5. That's fine — confirms pytest discovers our config.

- [ ] **Step 8: Commit**

```powershell
git add pyproject.toml .gitignore src tests scripts uv.lock
git commit -m "feat: project scaffold (uv, pytest, playwright)"
```

---

## Task 2: Capture HTML Fixture

**Why:** All parse tests run against captured HTML. We need one real fixture committed to the repo so tests are reproducible without a live browser.

**Files:**
- Create: `scripts/capture_fixture.py`
- Create (output): `tests/fixtures/meteoblue.html`

- [ ] **Step 1: Write the capture script**

Path: `scripts/capture_fixture.py`

```python
"""One-shot script to capture meteoblue HTML for use as test fixture.

Run: uv run python scripts/capture_fixture.py

Captures the page after toggling 3h → 1h. Re-run any time the layout
appears to change, then update assertions in tests/test_parse.py.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://www.meteoblue.com/en/weather/week/north-melbourne_australia_2154912"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "meteoblue.html"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(URL, wait_until="networkidle")
            page.evaluate(
                "document.querySelectorAll('.fc-consent-root').forEach(e => e.remove())"
            )
            page.locator("label.switch-with-label").first.click()
            page.locator("table.hourlywind").wait_for(state="visible", timeout=5000)
            html = page.content()
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(html, encoding="utf-8")
            print(f"Wrote {OUT} ({len(html):,} chars)")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the capture script**

```powershell
uv run python scripts/capture_fixture.py
```

Expected: prints `Wrote .../tests/fixtures/meteoblue.html (XX,XXX chars)`. File should be 100KB+.

- [ ] **Step 3: Sanity-check the fixture contains expected markers**

```powershell
Select-String -Path tests\fixtures\meteoblue.html -Pattern 'table class="hourlywind"' -SimpleMatch
Select-String -Path tests\fixtures\meteoblue.html -Pattern 'id="day1"' -SimpleMatch
Select-String -Path tests\fixtures\meteoblue.html -Pattern 'id="day2"' -SimpleMatch
```

Expected: each pattern found.

- [ ] **Step 4: Note the captured peak rain values**

Open `tests/fixtures/meteoblue.html` and search for the `table.hourlywind` row containing percentages. Note the highest `%` value and the column index of its first occurrence (count from the header row's hour labels). Record these as variables for use in Task 5:

- `EXPECTED_PEAK_PCT` = (e.g. 88)
- `EXPECTED_PEAK_TIME` = (e.g. "12:00", from the column whose header is `1200`)

If the live page shows different values, that's fine — those become the test expectations.

- [ ] **Step 5: Commit**

```powershell
git add scripts/capture_fixture.py tests/fixtures/meteoblue.html
git commit -m "test: capture meteoblue HTML fixture for parse tests"
```

---

## Task 3: Define Data Models

**Files:**
- Create: `src/burevestnik/models.py`

- [ ] **Step 1: Write a smoke test for the dataclasses**

Path: `tests/test_models.py`

```python
from burevestnik.models import DaySummary, Forecast


def test_day_summary_constructs():
    d = DaySummary(
        label="Today",
        weekday="Sun",
        temp_max_c=21,
        temp_min_c=15,
        wind_kmh_max=19,
        rain_mm_low=10.0,
        rain_mm_high=20.0,
        sun_hours=2.0,
    )
    assert d.temp_max_c == 21
    assert d.label == "Today"


def test_forecast_constructs():
    day = DaySummary(
        label="Today", weekday="Sun", temp_max_c=21, temp_min_c=15,
        wind_kmh_max=19, rain_mm_low=10.0, rain_mm_high=20.0, sun_hours=2.0,
    )
    f = Forecast(today=day, tomorrow=day, peak_rain_pct=88, peak_rain_time="12:00")
    assert f.peak_rain_pct == 88


def test_dataclasses_are_frozen():
    d = DaySummary(
        label="Today", weekday="Sun", temp_max_c=21, temp_min_c=15,
        wind_kmh_max=19, rain_mm_low=10.0, rain_mm_high=20.0, sun_hours=2.0,
    )
    import dataclasses
    try:
        d.temp_max_c = 99
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("DaySummary should be frozen")
```

- [ ] **Step 2: Run test, verify fails**

```powershell
uv run pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'burevestnik.models'`

- [ ] **Step 3: Implement the models**

Path: `src/burevestnik/models.py`

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DaySummary:
    label: str           # "Today" / "Tomorrow"
    weekday: str         # "Sun"
    temp_max_c: int
    temp_min_c: int
    wind_kmh_max: int
    rain_mm_low: float
    rain_mm_high: float
    sun_hours: float


@dataclass(frozen=True)
class Forecast:
    today: DaySummary
    tomorrow: DaySummary
    peak_rain_pct: int          # max % across today's 1-hour slots
    peak_rain_time: str         # "HH:MM" — the slot where peak hit; "" if no rain
```

- [ ] **Step 4: Run test, verify passes**

```powershell
uv run pytest tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/burevestnik/models.py tests/test_models.py
git commit -m "feat: add Forecast and DaySummary dataclasses"
```

---

## Task 4: parse.parse_day

**Goal:** Extract a `DaySummary` from the `#day1` or `#day2` element of the captured HTML.

**Approach:** The day tab's text content matches a stable pattern (e.g. `"Sun Today 21 °C 15 °C 19 km/h 10-20 mm 2 h"`). We normalize whitespace and use targeted regexes. This is more robust against meteoblue's CSS class churn than digging into specific span selectors.

**Files:**
- Create: `src/burevestnik/parse.py`
- Create: `tests/test_parse.py`

- [ ] **Step 1: Write the failing tests for `parse_day`**

Path: `tests/test_parse.py`

```python
from pathlib import Path
import pytest
from burevestnik.parse import parse_day

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
    assert day.wind_kmh_max > 0
    assert day.sun_hours >= 0


def test_parse_day_today_extracts_rain_range():
    day = parse_day(FIXTURE, "#day1")
    assert day.rain_mm_low >= 0
    assert day.rain_mm_high >= day.rain_mm_low


def test_parse_day_tomorrow_has_label():
    day = parse_day(FIXTURE, "#day2")
    # Tomorrow tab includes the literal string "Tomorrow"
    assert day.label == "Tomorrow"


def test_parse_day_raises_on_missing_selector():
    with pytest.raises(ValueError, match="no element"):
        parse_day(FIXTURE, "#day99")
```

- [ ] **Step 2: Run test, verify fails**

```powershell
uv run pytest tests/test_parse.py -v
```

Expected: `ModuleNotFoundError: No module named 'burevestnik.parse'`

- [ ] **Step 3: Implement `parse_day`**

Path: `src/burevestnik/parse.py`

```python
"""Pure HTML → typed forecast data.

No I/O, no browser. All inputs are HTML strings; outputs are dataclasses.
"""
import re
from selectolax.parser import HTMLParser

from burevestnik.models import DaySummary

_TEMP_RE = re.compile(r"(-?\d+)\s*°C")
_WIND_RE = re.compile(r"(\d+)\s*km/h")
_RAIN_RE = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*mm")
_SUN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*h\b")


def parse_day(html: str, selector: str) -> DaySummary:
    """Extract a DaySummary from a #dayN tab's text content.

    Expected text shape after whitespace normalization:
      "<weekday> <label> <max>°C <min>°C <wind> km/h <rain> mm <sun> h"
    e.g. "Sun Today 21 °C 15 °C 19 km/h 10-20 mm 2 h"
    """
    doc = HTMLParser(html)
    el = doc.css_first(selector)
    if el is None:
        raise ValueError(f"no element matching {selector!r}")

    text = " ".join(el.text(strip=True).split())
    tokens = text.split()
    if len(tokens) < 2:
        raise ValueError(f"unexpected day tab text: {text!r}")
    weekday, label = tokens[0], tokens[1]

    temps = _TEMP_RE.findall(text)
    if len(temps) < 2:
        raise ValueError(f"expected two °C values in {text!r}")
    temp_max_c, temp_min_c = int(temps[0]), int(temps[1])

    wind_match = _WIND_RE.search(text)
    if wind_match is None:
        raise ValueError(f"no wind speed in {text!r}")
    wind_kmh_max = int(wind_match.group(1))

    rain_match = _RAIN_RE.search(text)
    if rain_match is None:
        raise ValueError(f"no rain mm in {text!r}")
    rain_mm_low = float(rain_match.group(1))
    rain_mm_high = float(rain_match.group(2)) if rain_match.group(2) else rain_mm_low

    sun_match = _SUN_RE.search(text)
    if sun_match is None:
        raise ValueError(f"no sun hours in {text!r}")
    sun_hours = float(sun_match.group(1))

    return DaySummary(
        label=label,
        weekday=weekday,
        temp_max_c=temp_max_c,
        temp_min_c=temp_min_c,
        wind_kmh_max=wind_kmh_max,
        rain_mm_low=rain_mm_low,
        rain_mm_high=rain_mm_high,
        sun_hours=sun_hours,
    )
```

- [ ] **Step 4: Run test, verify passes**

```powershell
uv run pytest tests/test_parse.py -v
```

Expected: 5 passed. If the regex doesn't match the actual fixture (selectors changed), inspect the failing test's `text` value (`pytest -v` shows the raised ValueError text) and adjust the regex.

- [ ] **Step 5: Commit**

```powershell
git add src/burevestnik/parse.py tests/test_parse.py
git commit -m "feat(parse): extract DaySummary from day tab"
```

---

## Task 5: parse.parse_peak_rain

**Goal:** Find the highest rain-probability hour from `table.hourlywind`.

**Approach:** The hourly table has a row of percentage cells (one per hour). Identify the row by detecting which row's data cells overwhelmingly contain "%". The header row contains hour labels formatted as `"01 00"`, `"02 00"`, ..., which we convert to `"HH:00"`. Earliest hour wins on tie.

**Files:**
- Modify: `src/burevestnik/parse.py`
- Modify: `tests/test_parse.py`

- [ ] **Step 1: Add the failing tests for `parse_peak_rain`**

Append to `tests/test_parse.py`:

```python
from burevestnik.parse import parse_peak_rain


def test_parse_peak_rain_returns_int_and_hh_mm():
    pct, t = parse_peak_rain(FIXTURE)
    assert isinstance(pct, int)
    assert 0 <= pct <= 100
    if pct > 0:
        # "HH:00"
        assert len(t) == 5 and t[2] == ":"
        hh = int(t[:2])
        assert 0 <= hh <= 24


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
```

- [ ] **Step 2: Run test, verify fails**

```powershell
uv run pytest tests/test_parse.py::test_parse_peak_rain_returns_int_and_hh_mm -v
```

Expected: `ImportError: cannot import name 'parse_peak_rain' from 'burevestnik.parse'`

- [ ] **Step 3: Implement `parse_peak_rain`**

Append to `src/burevestnik/parse.py`:

```python
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
            if 0 <= hh <= 24:
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
    for pct, hour in pcts:
        if pct == max_pct:
            return pct, hour
    return 0, ""
```

- [ ] **Step 4: Run tests, verify all pass**

```powershell
uv run pytest tests/test_parse.py -v
```

Expected: 9 passed (5 from Task 4 + 4 new).

- [ ] **Step 5: Commit**

```powershell
git add src/burevestnik/parse.py tests/test_parse.py
git commit -m "feat(parse): extract peak rain probability and hour"
```

---

## Task 6: parse.extract Orchestrator

**Goal:** Single entry point `extract(html) -> Forecast` that calls `parse_day` twice and `parse_peak_rain` once.

**Files:**
- Modify: `src/burevestnik/parse.py`
- Modify: `tests/test_parse.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_parse.py`:

```python
from burevestnik.parse import extract
from burevestnik.models import Forecast


def test_extract_returns_full_forecast():
    f = extract(FIXTURE)
    assert isinstance(f, Forecast)
    assert f.today.label == "Today"
    assert f.tomorrow.label == "Tomorrow"
    assert 0 <= f.peak_rain_pct <= 100
```

- [ ] **Step 2: Run test, verify fails**

```powershell
uv run pytest tests/test_parse.py::test_extract_returns_full_forecast -v
```

Expected: `ImportError: cannot import name 'extract'`

- [ ] **Step 3: Implement `extract`**

In `src/burevestnik/parse.py`, change the existing import line:

```python
from burevestnik.models import DaySummary
```

to:

```python
from burevestnik.models import DaySummary, Forecast
```

Then append the function at the bottom of the file:

```python
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
```

- [ ] **Step 4: Run all parse tests, verify pass**

```powershell
uv run pytest tests/test_parse.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/burevestnik/parse.py tests/test_parse.py
git commit -m "feat(parse): add extract() orchestrator returning Forecast"
```

---

## Task 7: caption.render — Happy Path

**Goal:** Pure function `render(forecast, now) -> str` producing the HTML-formatted caption per spec §6.1.

**Files:**
- Create: `src/burevestnik/caption.py`
- Create: `tests/test_caption.py`

- [ ] **Step 1: Write the failing test**

Path: `tests/test_caption.py`

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from burevestnik.caption import render
from burevestnik.models import DaySummary, Forecast


def _make_forecast(peak_pct: int = 88, peak_time: str = "12:00") -> Forecast:
    today = DaySummary(
        label="Today", weekday="Sun",
        temp_max_c=21, temp_min_c=15,
        wind_kmh_max=19,
        rain_mm_low=10.0, rain_mm_high=20.0,
        sun_hours=2.0,
    )
    tomorrow = DaySummary(
        label="Tomorrow", weekday="Mon",
        temp_max_c=17, temp_min_c=13,
        wind_kmh_max=22,
        rain_mm_low=0.0, rain_mm_high=2.0,
        sun_hours=6.0,
    )
    return Forecast(today=today, tomorrow=tomorrow,
                    peak_rain_pct=peak_pct, peak_rain_time=peak_time)


def test_render_full_template():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now)

    # Header line
    assert "<b>North Melbourne</b>" in out
    assert "Sunday" in out
    assert "3 May" in out

    # Today temps
    assert "<b>21°</b>" in out
    assert "Low 15°" in out

    # Rain line
    assert "10–20mm" in out                 # en-dash
    assert "<b>88%</b>" in out
    assert "at 12:00" in out

    # Wind
    assert "Wind up to 19km/h" in out

    # Sun line — sunrise/sunset just need to be HH:MM format
    assert "Sun 2h" in out
    import re
    assert re.search(r"🌅 \d{2}:\d{2}", out)
    assert re.search(r"🌇 \d{2}:\d{2}", out)

    # Tomorrow line
    assert "<i>Tomorrow:</i> 17°/13°" in out
    assert "0–2mm" in out
    assert "wind 22km/h" in out

    # Updated stamp
    assert "Updated 14:32" in out
    assert "AEST" in out  # May is standard time in Melbourne


def test_caption_under_1024_chars():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    out = render(_make_forecast(), now)
    assert len(out) <= 1024, f"caption is {len(out)} chars (Telegram max 1024)"
```

- [ ] **Step 2: Run test, verify fails**

```powershell
uv run pytest tests/test_caption.py -v
```

Expected: `ModuleNotFoundError: No module named 'burevestnik.caption'`

- [ ] **Step 3: Implement `render`**

Path: `src/burevestnik/caption.py`

```python
"""Pure caption rendering. Takes a Forecast and a datetime, returns HTML string.

Telegram caption limit is 1024 chars; output must stay under that.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

from burevestnik.models import Forecast

MELBOURNE = LocationInfo(
    name="Melbourne",
    region="Australia",
    timezone="Australia/Melbourne",
    latitude=-37.81,
    longitude=144.96,
)
MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")


def _format_rain_range(low: float, high: float) -> str:
    low_i, high_i = round(low), round(high)
    if low_i == high_i:
        return f"{low_i}mm"
    return f"{low_i}–{high_i}mm"


def _sunrise_sunset(now: datetime) -> tuple[str, str] | tuple[None, None]:
    try:
        s = sun(MELBOURNE.observer, date=now.date(), tzinfo=MELBOURNE_TZ)
        return s["sunrise"].strftime("%H:%M"), s["sunset"].strftime("%H:%M")
    except Exception:
        return None, None


def render(forecast: Forecast, now: datetime) -> str:
    today = forecast.today
    tomorrow = forecast.tomorrow

    weekday_long = now.strftime("%A")
    date_str = f"{now.day} {now.strftime('%B')}"

    sunrise, sunset = _sunrise_sunset(now)

    lines: list[str] = []
    lines.append(f"🌦 <b>North Melbourne</b> · {weekday_long}, {date_str}")
    lines.append("")
    lines.append(f"🌡 High <b>{round(today.temp_max_c)}°</b> / Low {round(today.temp_min_c)}°")

    if forecast.peak_rain_pct > 0:
        rain_str = _format_rain_range(today.rain_mm_low, today.rain_mm_high)
        lines.append(
            f"☔ Rain {rain_str} · Peak <b>{forecast.peak_rain_pct}%</b> "
            f"at {forecast.peak_rain_time}"
        )

    lines.append(f"💨 Wind up to {round(today.wind_kmh_max)}km/h")

    if sunrise is not None and sunset is not None:
        lines.append(
            f"☀ Sun {round(today.sun_hours)}h · 🌅 {sunrise} · 🌇 {sunset}"
        )

    lines.append("")
    tomorrow_rain = _format_rain_range(tomorrow.rain_mm_low, tomorrow.rain_mm_high)
    lines.append(
        f"<i>Tomorrow:</i> {round(tomorrow.temp_max_c)}°/{round(tomorrow.temp_min_c)}° "
        f"· {tomorrow_rain} · wind {round(tomorrow.wind_kmh_max)}km/h"
    )
    lines.append("")
    lines.append(f"<i>Updated {now.strftime('%H:%M %Z')}</i>")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests, verify pass**

```powershell
uv run pytest tests/test_caption.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/burevestnik/caption.py tests/test_caption.py
git commit -m "feat(caption): render full caption template"
```

---

## Task 8: caption Edge Cases

**Goal:** Handle (a) collapsed rain range when low == high, (b) drop ☔ line when peak == 0%, (c) drop ☀ line when astral returns nothing.

The implementation in Task 7 already handles all three cases. This task adds explicit tests to lock the behavior in.

**Files:**
- Modify: `tests/test_caption.py`

- [ ] **Step 1: Add tests for the three edge cases**

Append to `tests/test_caption.py`:

```python
from unittest.mock import patch


def test_collapses_equal_rain_range():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(peak_pct=50, peak_time="12:00")
    # Replace today with rain_mm_low == rain_mm_high
    today = DaySummary(
        label="Today", weekday="Sun",
        temp_max_c=21, temp_min_c=15, wind_kmh_max=19,
        rain_mm_low=5.0, rain_mm_high=5.0, sun_hours=2.0,
    )
    f = Forecast(today=today, tomorrow=f.tomorrow,
                 peak_rain_pct=f.peak_rain_pct, peak_rain_time=f.peak_rain_time)
    out = render(f, now)
    assert "5mm" in out
    assert "5–5mm" not in out
    assert "5-5mm" not in out


def test_drops_rain_line_when_zero_peak():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast(peak_pct=0, peak_time="")
    out = render(f, now)
    assert "☔" not in out
    assert "Peak" not in out
    # Other lines still present
    assert "🌡" in out
    assert "💨" in out


def test_drops_sun_line_when_astral_unavailable():
    now = datetime(2026, 5, 3, 14, 32, tzinfo=ZoneInfo("Australia/Melbourne"))
    f = _make_forecast()
    with patch("burevestnik.caption._sunrise_sunset", return_value=(None, None)):
        out = render(f, now)
    assert "☀" not in out
    assert "🌅" not in out
    assert "🌇" not in out
    # Wind/temp/tomorrow still present
    assert "💨" in out
    assert "Tomorrow:" in out
```

- [ ] **Step 2: Run tests, verify pass (no implementation change needed)**

```powershell
uv run pytest tests/test_caption.py -v
```

Expected: 5 passed (2 from Task 7 + 3 new). If `test_collapses_equal_rain_range` fails because rain_mm_low/high are floats and `round(5.0) == 5`, the existing implementation's `round()` already handles it; if it doesn't, fix `_format_rain_range` to compare rounded values (already does).

- [ ] **Step 3: Commit**

```powershell
git add tests/test_caption.py
git commit -m "test(caption): cover rain-range collapse, no-rain, no-sun edge cases"
```

---

## Task 9: scrape.fetch

**Goal:** Wrap Playwright in a single function returning `(html, jpeg_bytes)`. No automated test (requires live browser); covered by manual smoke + the integration check in Task 14.

**Files:**
- Create: `src/burevestnik/scrape.py`

- [ ] **Step 1: Implement `fetch`**

Path: `src/burevestnik/scrape.py`

```python
"""Playwright I/O for meteoblue. Returns rendered HTML and a JPEG screenshot.

This module is the only one with browser side effects. parse.py / caption.py
work entirely on its outputs.
"""
from playwright.sync_api import sync_playwright


def fetch(url: str) -> tuple[str, bytes]:
    """Open URL, dismiss cookie banner, toggle to 1h view, screenshot the table.

    Returns (rendered_html, jpeg_bytes). Raises if the toggle or table never
    appears within 5 seconds (treated as a meteoblue layout change).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="networkidle")
            page.evaluate(
                "document.querySelectorAll('.fc-consent-root')"
                ".forEach(e => e.remove())"
            )
            page.locator("label.switch-with-label").first.click()
            page.locator("table.hourlywind").wait_for(state="visible", timeout=5000)
            html = page.content()
            jpeg = page.locator("table.hourlywind").screenshot(
                type="jpeg", quality=90
            )
            return html, jpeg
        finally:
            browser.close()
```

- [ ] **Step 2: Manual smoke test**

```powershell
uv run python -c "from burevestnik.scrape import fetch; h, j = fetch('https://www.meteoblue.com/en/weather/week/north-melbourne_australia_2154912'); print(f'html: {len(h):,} chars, jpeg: {len(j):,} bytes')"
```

Expected: prints something like `html: 250,000 chars, jpeg: 50,000 bytes`. Run takes 15-25 seconds.

- [ ] **Step 3: Save the smoke output as a sanity image**

```powershell
uv run python -c "from burevestnik.scrape import fetch; from pathlib import Path; h, j = fetch('https://www.meteoblue.com/en/weather/week/north-melbourne_australia_2154912'); Path('smoke.jpeg').write_bytes(j); print('wrote smoke.jpeg')"
```

Open `smoke.jpeg` and visually confirm it's the 1-hourly table (24 hourly columns, not 8 three-hourly ones). Delete the file after verification:

```powershell
Remove-Item smoke.jpeg
```

- [ ] **Step 4: Commit**

```powershell
git add src/burevestnik/scrape.py
git commit -m "feat(scrape): fetch HTML + JPEG of 1h forecast table"
```

---

## Task 10: telegram.send_photo

**Goal:** One thin `httpx.post` to `sendPhoto`. No automated test (would just verify httpx works); covered by main.py integration.

**Files:**
- Create: `src/burevestnik/telegram.py`

- [ ] **Step 1: Implement `send_photo`**

Path: `src/burevestnik/telegram.py`

```python
"""Telegram Bot API: sendPhoto with multipart upload.

Single function, single POST. We deliberately don't use python-telegram-bot
(heavyweight async runtime). httpx is enough.
"""
import httpx

API_URL = "https://api.telegram.org/bot{token}/sendPhoto"


def send_photo(token: str, chat_id: str, image: bytes, caption: str) -> None:
    """POST sendPhoto. Raises on non-2xx (caller decides how to handle).

    `chat_id` may be a numeric string like '-1001234567890' for private channels
    or a username like '@my_channel' for public ones.
    """
    response = httpx.post(
        API_URL.format(token=token),
        data={
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"photo": ("forecast.jpg", image, "image/jpeg")},
        timeout=30.0,
    )
    response.raise_for_status()
```

- [ ] **Step 2: Lint-check by importing**

```powershell
uv run python -c "from burevestnik.telegram import send_photo; print(send_photo.__doc__.split('.')[0])"
```

Expected: prints `POST sendPhoto`.

- [ ] **Step 3: Commit**

```powershell
git add src/burevestnik/telegram.py
git commit -m "feat(telegram): add sendPhoto wrapper"
```

---

## Task 11: main.py — Orchestrator + DST Gate

**Goal:** Entry point that gates on Melbourne local hour, then invokes scrape → parse → caption → telegram.

**Files:**
- Create: `src/burevestnik/main.py`
- Create: `tests/test_main.py` (gate test only)

- [ ] **Step 1: Write a unit test for the DST gate**

Path: `tests/test_main.py`

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from burevestnik.main import is_posting_hour


def test_posting_hours_match_spec():
    tz = ZoneInfo("Australia/Melbourne")
    for hour in (6, 9, 12, 15, 18):
        assert is_posting_hour(datetime(2026, 5, 3, hour, 0, tzinfo=tz))


def test_non_posting_hours_skip():
    tz = ZoneInfo("Australia/Melbourne")
    for hour in (0, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 23):
        assert not is_posting_hour(datetime(2026, 5, 3, hour, 0, tzinfo=tz))
```

- [ ] **Step 2: Run test, verify fails**

```powershell
uv run pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'burevestnik.main'`

- [ ] **Step 3: Implement `main.py`**

Path: `src/burevestnik/main.py`

```python
"""Entry point. Reads env, gates on Melbourne local hour, posts to Telegram.

Run: uv run python -m burevestnik.main
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from burevestnik import caption, parse, scrape, telegram

MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")
POSTING_HOURS = frozenset({6, 9, 12, 15, 18})
DEFAULT_URL = (
    "https://www.meteoblue.com/en/weather/week/north-melbourne_australia_2154912"
)


def is_posting_hour(now: datetime) -> bool:
    """True iff `now` (Melbourne local time) is one of the configured posting hours."""
    return now.hour in POSTING_HOURS


def main() -> int:
    print("boot")

    now = datetime.now(MELBOURNE_TZ)
    if not is_posting_hour(now):
        print(f"Melbourne hour: {now.hour} — skipping")
        return 0
    print(f"Melbourne hour: {now.hour} — posting")

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = os.environ.get("METEOBLUE_URL", DEFAULT_URL)

    html, jpeg = scrape.fetch(url)
    print(f"scraped: {len(jpeg):,} jpeg bytes")

    forecast = parse.extract(html)
    print(
        f"parsed: today {forecast.today.temp_max_c}°/{forecast.today.temp_min_c}°, "
        f"peak rain {forecast.peak_rain_pct}% at {forecast.peak_rain_time or 'n/a'}"
    )

    text = caption.render(forecast, now)
    print(f"caption: {len(text)} chars")

    telegram.send_photo(token, chat_id, jpeg, text)
    print("telegram: 200 OK")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests, verify pass**

```powershell
uv run pytest -v
```

Expected: all tests pass (10 parse + 5 caption + 3 models + 2 main = 20).

- [ ] **Step 5: Commit**

```powershell
git add src/burevestnik/main.py tests/test_main.py
git commit -m "feat(main): orchestrator + Melbourne DST gate"
```

---

## Task 12: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/post.yml`

- [ ] **Step 1: Write the workflow**

Path: `.github/workflows/post.yml`

```yaml
name: Post weather to Telegram

on:
  schedule:
    - cron: '5 * * * *'   # every UTC hour at :05; main.py gates on Melbourne local hour
  workflow_dispatch: {}   # manual trigger for testing
  push:
    branches: [main]      # CI test on push (skips cron logic)

jobs:
  post:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Install Python deps
        run: uv sync --extra dev --frozen

      - name: Run tests
        if: github.event_name == 'push'
        run: uv run pytest

      - name: Install Chromium
        if: github.event_name != 'push'
        run: uv run playwright install --with-deps chromium

      - name: Post to Telegram
        if: github.event_name != 'push'
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: uv run python -m burevestnik.main
```

- [ ] **Step 2: Sanity-check the workflow file is well-formed**

PyYAML isn't (and shouldn't be) a dep, so validate via `actionlint` if available, or just confirm GitHub accepts it once pushed (the next step). For a local quick check that the file is at least readable:

```powershell
Get-Content .github/workflows/post.yml | Select-Object -First 5
```

Expected: prints the first five lines starting with `name: Post weather to Telegram`.

- [ ] **Step 3: Commit**

```powershell
git add .github/workflows/post.yml
git commit -m "ci: GitHub Actions cron for hourly Telegram post"
```

---

## Task 13: README — Bot/Channel Setup Instructions

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

Path: `README.md`

````markdown
# Burevestnik

Telegram bot that posts a 1-hourly weather forecast for North Melbourne to a private channel, 5 times per day. Runs on GitHub Actions cron — no server needed.

See `meteo-plan.md` for full design rationale; `meteo-implementation-plan.md` for build steps.

## What it posts

- A JPEG screenshot of meteoblue's 1-hourly forecast table.
- A rich text caption with today's high/low, peak rain probability and time, wind, sunrise/sunset, and a one-line tomorrow brief.

Posting times (Melbourne local): **06:00, 09:00, 12:00, 15:00, 18:00**, every day. DST is handled automatically.

## One-time setup

### 1. Create the Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram → send `/newbot`.
2. Choose a name and username (must end in `bot`).
3. **Save the token** that BotFather gives you — looks like `123456:ABC-DEF...`.

### 2. Create the channel

1. In Telegram → New Channel → **Private**.
2. Open the channel → settings → Administrators → Add admin → search your bot's username → grant **Post Messages** only (no other permissions needed).

### 3. Get the channel ID

1. Post any message in your new channel from your own account.
2. Forward that message to [@RawDataBot](https://t.me/RawDataBot) (or [@JsonDumpBot](https://t.me/JsonDumpBot)).
3. The bot returns a JSON dump. Find `forward_from_chat.id` — it's a negative integer like `-1001234567890`. **Save it.**

### 4. Configure the GitHub repo

1. Push this repo to GitHub (private is fine).
2. Repo settings → Secrets and variables → Actions → New repository secret. Add:
   - `TELEGRAM_BOT_TOKEN` — the bot token from step 1.
   - `TELEGRAM_CHAT_ID` — the channel ID from step 3.
3. Actions → "Post weather to Telegram" → Run workflow → manually trigger once to verify.

After verification, the cron schedule takes over.

## Local development

```powershell
uv sync --extra dev
uv run playwright install chromium
uv run pytest
```

Run a one-off post locally (requires both env vars set):

```powershell
$env:TELEGRAM_BOT_TOKEN = "..."
$env:TELEGRAM_CHAT_ID = "..."
uv run python -m burevestnik.main
```

Note: the local run will skip if the current Melbourne hour isn't in `{6, 9, 12, 15, 18}`. To force a post for testing, temporarily edit `POSTING_HOURS` in `src/burevestnik/main.py`.

## Re-capturing the test fixture

If meteoblue changes their layout and parse tests start failing:

```powershell
uv run python scripts/capture_fixture.py
uv run pytest    # update assertions in tests/test_parse.py if values changed
```
````

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "docs: README with setup steps and local dev"
```

---

## Task 14: End-to-End Smoke Test

**Goal:** Run the full pipeline once with real credentials, verify a post lands in the channel.

**Files:** (none — operational verification)

- [ ] **Step 1: Confirm secrets are set**

```powershell
# In the repo on GitHub, verify both secrets exist:
# Settings → Secrets and variables → Actions → Repository secrets
# Should see: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

- [ ] **Step 2: Manually trigger the workflow**

GitHub repo → Actions tab → "Post weather to Telegram" → Run workflow → branch `main`.

Watch the run. Expected log lines:
```
boot
Melbourne hour: <N> — posting   (or "skipping" if outside posting hours)
scraped: XX,XXX jpeg bytes
parsed: today 21°/15°, peak rain 88% at 12:00
caption: 421 chars
telegram: 200 OK
done
```

If the hour isn't a posting hour, the workflow exits 0 with `Melbourne hour: N — skipping`. To force a test post, temporarily change `POSTING_HOURS` to `frozenset(range(24))` and re-run, then revert.

- [ ] **Step 3: Verify the post appears in the channel**

Open the private channel in Telegram. You should see:
- A JPEG image of the 1-hourly forecast table.
- A caption matching the rendered template (header, temps, rain line, wind, sun line, tomorrow brief, updated stamp).

- [ ] **Step 4: Commit any tweaks** (if forcing posting hours required code change, revert it)

```powershell
git status
# If POSTING_HOURS was reverted:
git diff src/burevestnik/main.py        # should be empty
```

If everything passed, the cron will take over automatically. The bot is live.

---

## Self-Review Checklist (filled in by writing-plans skill)

- **Spec coverage:** every section of `meteo-plan.md` mapped to a task:
  - §1 Goals/Scope → Tasks 1-12 collectively.
  - §2 Architecture → Tasks 9-11 (modules) + Task 12 (cron).
  - §3 File Layout → Task 1 scaffold + each module's task.
  - §4 Components/Dataclasses → Task 3 (models), Tasks 4-11 (modules).
  - §5 Data Flow → Task 11 (orchestrator).
  - §6 Caption Format → Tasks 7-8.
  - §6.3 Edge cases (rain collapse, drop rain line, drop sun line) → Task 8.
  - §7 Configuration & Secrets → Task 13 README + Task 12 workflow secrets.
  - §8 Error Handling (fail loud, no retries) → naturally handled — none of the modules catch and swallow; httpx `raise_for_status()`, Playwright `wait_for` raises on timeout, parse functions raise `ValueError` on malformed input.
  - §9 Testing → Tasks 3, 4, 5, 6, 7, 8, 11.
  - §10 GitHub Actions → Task 12.
- **No placeholders:** every code block is complete and runnable.
- **Type consistency:** `DaySummary` field names (`temp_max_c`, `temp_min_c`, `wind_kmh_max`, `rain_mm_low`, `rain_mm_high`, `sun_hours`) used identically across `models.py`, `parse.py`, `caption.py`, and tests. `Forecast` field names (`today`, `tomorrow`, `peak_rain_pct`, `peak_rain_time`) likewise.
