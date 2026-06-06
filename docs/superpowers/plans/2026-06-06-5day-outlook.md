# 5-day Outlook Post Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On Monday and Thursday mornings, post an extra Telegram photo — the meteoblue meteogram cropped to its temperature panel — captioned with a compact 5-day per-day summary, sent before the normal daily forecast.

**Architecture:** Four pure/edge additions mirroring the existing pipeline. `scrape.fetch_meteogram` (browser I/O) returns page HTML + a vertically-cropped JPEG of the meteogram. `parse.parse_days` (pure) returns 5 `DaySummary`. `caption.render_outlook` (pure) renders the caption. `main.should_post_outlook` gates the new branch, which `main._post_outlook` orchestrates, wrapped best-effort so a failure never blocks the daily post.

**Tech Stack:** Python 3.12, Playwright (sync), selectolax, httpx, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-06-5day-outlook-design.md`. Crop target: `docs/superpowers/specs/2026-06-06-5day-outlook-crop-sample.png`.

**Branch:** `feature/weekly-5day-forecast` (already checked out).

**Conventions:**
- Run tests with `uv run pytest`. Single test: `uv run pytest tests/test_x.py::test_name -v`.
- All pure-function tests run against `tests/fixtures/meteoblue.html` — **never** re-run `scripts/capture_fixture.py`; it would overwrite the fixture and break the locked assertions below.

---

### Task 1: `parse_days` — extract N day summaries

**Files:**
- Modify: `src/burevestnik/parse.py` (add `parse_days` near `extract`, end of file)
- Test: `tests/test_parse.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_parse.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parse.py -k parse_days -v`
Expected: FAIL with `ImportError` / `cannot import name 'parse_days'`.

- [ ] **Step 3: Implement `parse_days`**

Add to `src/burevestnik/parse.py`, immediately above `def extract(`:

```python
def parse_days(html: str, count: int = 5) -> list[DaySummary]:
    """Extract the first `count` day-tab summaries (#day1 … #day{count}).

    Reuses parse_day per tab. #day1 is always today, so the list is the next
    `count` days in order from whatever day the page was fetched on. Raises
    ValueError (via parse_day) if any expected tab is missing.
    """
    return [parse_day(html, f"#day{n}") for n in range(1, count + 1)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_parse.py -k parse_days -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/burevestnik/parse.py tests/test_parse.py
git commit -m "feat(parse): add parse_days for N-day summaries"
```

---

### Task 2: `render_outlook` — compact 5-day caption

**Files:**
- Modify: `src/burevestnik/caption.py` (add `render_outlook` at end)
- Test: `tests/test_caption.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_caption.py`:

```python
from pathlib import Path

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_caption.py -k outlook -v`
Expected: FAIL with `cannot import name 'render_outlook'`.

- [ ] **Step 3: Implement `render_outlook`**

Add to the end of `src/burevestnik/caption.py`:

```python
def render_outlook(
    days: list[DaySummary],
    now: datetime,
    source_url: str,
) -> str:
    """Render a compact 5-day outlook caption (one line per day).

    No header line; each day is `<emoji> <Weekday> <hi>°/<lo>° <rain> ☀ <sun>h`,
    wind omitted to keep each day on one mobile line. Same footer as the daily
    caption. Stays well under Telegram's 1024-char limit for 5 days.
    """
    lines: list[str] = []
    for day in days:
        emoji = _condition_emoji(day.condition)
        if day.rain_mm_high == 0:
            rain = "no rain"
        else:
            rain = f"☔ {_format_rain_range(day.rain_mm_low, day.rain_mm_high)}"
        lines.append(
            f"{emoji} {day.weekday} {day.temp_max_c}°/{day.temp_min_c}° "
            f"{rain} ☀ {round(day.sun_hours)}h"
        )

    lines.append("")
    lines.append(
        f'<i>Updated {now.strftime("%H:%M %Z")} · '
        f'forecast by <a href="{html.escape(source_url, quote=True)}">meteoblue</a></i>'
    )
    return "\n".join(lines)
```

`_condition_emoji`, `_format_rain_range`, `html`, and `datetime` are already imported at the top of `caption.py`. **Also add `DaySummary` to the models import** (`caption.py` currently imports only `Forecast`): change `from burevestnik.models import Forecast` → `from burevestnik.models import DaySummary, Forecast`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_caption.py -k outlook -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/burevestnik/caption.py tests/test_caption.py
git commit -m "feat(caption): add render_outlook for 5-day summary"
```

---

### Task 3: `should_post_outlook` — Mon/Thu morning gate

**Files:**
- Modify: `src/burevestnik/main.py` (add helper near `should_forecast_tomorrow`)
- Test: `tests/test_main.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_main.py`:

```python
from burevestnik.main import should_post_outlook

# Fixture confirms 2026-05-05 is a Tuesday → 05-04 Mon, 05-07 Thu, 05-05 Tue.


def test_should_post_outlook_true_monday_morning():
    assert should_post_outlook(datetime(2026, 5, 4, 4, 17, tzinfo=_TZ)) is True


def test_should_post_outlook_true_thursday_morning():
    assert should_post_outlook(datetime(2026, 5, 7, 4, 17, tzinfo=_TZ)) is True


def test_should_post_outlook_false_monday_after_cutoff():
    assert should_post_outlook(datetime(2026, 5, 4, 16, 0, tzinfo=_TZ)) is False


def test_should_post_outlook_false_thursday_after_cutoff():
    assert should_post_outlook(datetime(2026, 5, 7, 16, 0, tzinfo=_TZ)) is False


def test_should_post_outlook_false_other_weekday_morning():
    assert should_post_outlook(datetime(2026, 5, 5, 4, 17, tzinfo=_TZ)) is False  # Tue
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -k outlook -v`
Expected: FAIL with `cannot import name 'should_post_outlook'`.

- [ ] **Step 3: Implement `should_post_outlook`**

In `src/burevestnik/main.py`, add a constant beside `TOMORROW_CUTOFF_HOUR`:

```python
OUTLOOK_WEEKDAYS = (0, 3)  # Monday, Thursday (datetime.weekday(): Mon=0 … Sun=6)
```

and add this function directly after `should_forecast_tomorrow`:

```python
def should_post_outlook(now: datetime) -> bool:
    """Return True on the Monday/Thursday morning (today-mode) runs only.

    The extra 5-day outlook post fires once on those mornings, before the daily
    forecast. The evening runs are tomorrow-mode and are excluded.
    """
    return now.weekday() in OUTLOOK_WEEKDAYS and not should_forecast_tomorrow(now)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -k outlook -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/burevestnik/main.py tests/test_main.py
git commit -m "feat(main): add should_post_outlook Mon/Thu gate"
```

---

### Task 4: `scrape.fetch_meteogram` — cropped meteogram screenshot

**Files:**
- Modify: `src/burevestnik/scrape.py` (extract shared setup; add `fetch_meteogram`)

No unit test: the meteogram is JS-hydrated and absent from the static fixture, so this is verified by live capture (Step 4) and `workflow_dispatch`, exactly like today's `table.hourlywind` screenshot.

- [ ] **Step 1: Extract shared browser setup into a context manager**

In `src/burevestnik/scrape.py`, add `from contextlib import contextmanager` to the imports, then add this helper above `def fetch(`:

```python
@contextmanager
def _browser_page():
    """Yield a Playwright page with metric-unit cookies + consent killer set.

    Shared by fetch() and fetch_meteogram() so the cookie seeding and the
    consent-overlay MutationObserver init script live in one place.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            context.add_cookies(
                [{**c, "domain": _COOKIE_DOMAIN, "path": "/"} for c in _UNIT_COOKIES]
            )
            context.add_init_script(_HIDE_CONSENT_SCRIPT)
            yield context.new_page()
        finally:
            context.close()
            browser.close()
```

Then replace the body of `fetch` so it uses the helper (behaviour unchanged — same waits, same screenshot):

```python
def fetch(url: str) -> tuple[str, bytes]:
    """Open URL, force metric units via cookies, toggle 1h view, screenshot.

    Returns (rendered_html, jpeg_bytes). Raises if the toggle or table never
    appears within 5 seconds (treated as a meteoblue layout change).
    """
    with _browser_page() as page:
        page.goto(url, wait_until="domcontentloaded")

        page.locator("label.switch-with-label").first.click()
        page.locator("table.hourlywind").wait_for(state="visible", timeout=5000)
        page.locator("div.uv-index").first.wait_for(state="attached", timeout=5000)
        page.locator(".fc-consent-root").wait_for(state="detached", timeout=5000)
        html = page.content()
        jpeg = page.locator("table.hourlywind").screenshot(type="jpeg", quality=90)
        return html, jpeg
```

- [ ] **Step 2: Add `fetch_meteogram`**

Add the crop fraction constants beneath `_COOKIE_DOMAIN`:

```python
# Vertical crop of the meteogram element, as fractions of its height, keeping
# just the temperature panel: from below the "Melbourne CBD"/logo title band
# (TOP) down to below the temperature panel's hour-tick row, before the
# precipitation panel (BOTTOM). The clouds + wind panels are dropped. Tuned
# against a live 650px render — see the crop sample under docs/superpowers/specs.
_TEMP_PANEL_TOP_FRACTION = 0.10
_TEMP_PANEL_BOTTOM_FRACTION = 0.42
```

Add after `fetch`. NOTE (discovered during live capture): the meteogram is
**lazy-loaded** — `#blooimage` holds only `<div class="loading">` until it is
scrolled into the viewport, so we must `scroll_into_view_if_needed()` *before*
waiting for the Highcharts SVG. The title band ("Melbourne CBD" + lat/lon +
logo) is part of the 650px SVG, so the crop needs a top offset (not just a
bottom cut) to match the sample, hence two fractions.

```python
def fetch_meteogram(url: str) -> tuple[str, bytes]:
    """Open URL, screenshot the meteogram cropped to its temperature panel.

    Returns (rendered_html, jpeg_bytes). The chart (#blooimage) is a lazy,
    JS-hydrated Highcharts SVG; we scroll it into view to trigger hydration,
    wait for it to render, then clip the temperature panel between the TOP and
    BOTTOM fractions of the element height. Raises if the chart never renders
    within 15 seconds (treated as a layout change).
    """
    with _browser_page() as page:
        page.goto(url, wait_until="domcontentloaded")

        # The meteogram is lazy-loaded: it only hydrates once scrolled into the
        # viewport, so scroll first, then wait for the Highcharts SVG to render.
        target = page.locator("#blooimage")
        target.scroll_into_view_if_needed()
        page.locator("#blooimage svg.highcharts-root").wait_for(
            state="visible", timeout=15000
        )
        page.locator(".fc-consent-root").wait_for(state="detached", timeout=5000)
        html = page.content()

        box = target.bounding_box()
        if box is None:
            raise RuntimeError("meteogram #blooimage has no bounding box")
        top = box["y"] + box["height"] * _TEMP_PANEL_TOP_FRACTION
        bottom = box["y"] + box["height"] * _TEMP_PANEL_BOTTOM_FRACTION
        clip = {
            "x": box["x"],
            "y": top,
            "width": box["width"],
            "height": bottom - top,
        }
        jpeg = page.screenshot(type="jpeg", quality=90, clip=clip)
        return html, jpeg
```

- [ ] **Step 3: Verify `fetch` still works (no fixture overwrite)**

Run (requires chromium + network; install once with `uv run playwright install chromium`):

```bash
uv run python -c "from burevestnik.scrape import fetch; h,j=fetch('https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810'); print('html', len(h), 'jpeg', len(j)); assert 'hourlywind' in h"
```

Expected: prints non-zero `html`/`jpeg` sizes, no assertion error. (This does **not** write the fixture.)

- [ ] **Step 4: Capture the cropped meteogram and tune the fraction**

```bash
uv run python -c "from burevestnik.scrape import fetch_meteogram; h,j=fetch_meteogram('https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810'); open('scratch_meteogram.jpg','wb').write(j); print('wrote', len(j), 'bytes')"
```

Open `scratch_meteogram.jpg` and compare to `docs/superpowers/specs/2026-06-06-5day-outlook-crop-sample.png`. Adjust `_TEMP_PANEL_FRACTION` (lower = less of the chart) until the crop ends just below the temperature panel's hour-tick row, before the cloud panel. Re-run until it matches. Then delete the scratch file:

```bash
rm scratch_meteogram.jpg
```

- [ ] **Step 5: Commit**

```bash
git add src/burevestnik/scrape.py
git commit -m "feat(scrape): add fetch_meteogram cropped to temperature panel"
```

---

### Task 5: `_post_outlook` orchestration

**Files:**
- Modify: `src/burevestnik/main.py` (add `_post_outlook`)
- Test: `tests/test_main.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main.py` (add `from pathlib import Path` at the top if not present):

```python
_FIXTURE = (Path(__file__).parent / "fixtures" / "meteoblue.html").read_text(encoding="utf-8")


def test_post_outlook_parses_renders_and_sends(monkeypatch):
    from burevestnik import main, scrape, telegram

    captured = {}
    monkeypatch.setattr(scrape, "fetch_meteogram", lambda url: (_FIXTURE, b"jpeg-bytes"))

    def fake_send(token, chat_id, image, caption):
        captured.update(token=token, chat_id=chat_id, image=image, caption=caption)

    monkeypatch.setattr(telegram, "send_photo", fake_send)

    now = datetime(2026, 5, 7, 4, 17, tzinfo=_TZ)
    main._post_outlook("tok", "@chan", "https://example.com/week", now)

    assert captured["token"] == "tok"
    assert captured["chat_id"] == "@chan"
    assert captured["image"] == b"jpeg-bytes"
    # Caption is the rendered 5-day outlook for the fixture days.
    assert "⛅ Tue 15°/12° no rain ☀ 2h" in captured["caption"]
    assert "🌧 Thu 10°/8° ☔ 5–10mm ☀ 0h" in captured["caption"]
    assert '<a href="https://example.com/week">meteoblue</a>' in captured["caption"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py::test_post_outlook_parses_renders_and_sends -v`
Expected: FAIL with `AttributeError: module 'burevestnik.main' has no attribute '_post_outlook'`.

- [ ] **Step 3: Implement `_post_outlook`**

In `src/burevestnik/main.py`, add after `_require_env` (the module already does `from burevestnik import caption, parse, scrape, telegram`):

```python
def _post_outlook(token: str, chat_id: str, source_url: str, now: datetime) -> None:
    """Post the 5-day outlook photo (cropped meteogram + per-day caption)."""
    html, jpeg = scrape.fetch_meteogram(source_url)
    days = parse.parse_days(html, 5)
    text = caption.render_outlook(days, now, source_url)
    print(f"outlook: {len(days)} days, {len(text)} caption chars")
    telegram.send_photo(token, chat_id, jpeg, text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py::test_post_outlook_parses_renders_and_sends -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/burevestnik/main.py tests/test_main.py
git commit -m "feat(main): add _post_outlook orchestration"
```

---

### Task 6: Wire the outlook branch into `main()` (best-effort)

**Files:**
- Modify: `src/burevestnik/main.py` (inside `main()`)

No new unit test: `main()` orchestration is not unit-tested in this codebase (its parts — `should_post_outlook`, `_post_outlook` — are). Verified end-to-end via `workflow_dispatch`.

- [ ] **Step 1: Add the branch before the daily flow**

In `src/burevestnik/main.py`, locate (inside `main()`):

```python
    token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")
    url = os.environ.get("METEOBLUE_URL", DEFAULT_URL)
```

Immediately **after** those three lines, insert:

```python
    # Mon/Thu mornings: post the 5-day outlook first. Best-effort — a failure
    # here (e.g. the meteogram not rendering) must never block the daily post.
    if should_post_outlook(now):
        print("outlook: posting 5-day overview")
        try:
            _post_outlook(token, chat_id, url, now)
            print("outlook: 200 OK")
        except Exception as exc:  # noqa: BLE001 — deliberately broad; daily post must proceed
            print(f"WARNING: outlook post failed, continuing to daily: {exc!r}")
```

- [ ] **Step 2: Verify the full test suite passes**

Run: `uv run pytest`
Expected: PASS — all existing tests plus the new `parse_days`, `render_outlook`, `should_post_outlook`, and `_post_outlook` tests.

- [ ] **Step 3: End-to-end smoke (optional, requires secrets + chromium)**

With `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` set and a frozen Monday/Thursday `now`, or simply trust the `workflow_dispatch` run. To force a local outlook post without waiting for Mon/Thu, temporarily test `_post_outlook` directly:

```bash
uv run python -c "from datetime import datetime; from zoneinfo import ZoneInfo; import os; from burevestnik.main import _post_outlook; _post_outlook(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], 'https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810', datetime.now(ZoneInfo('Australia/Melbourne')))"
```

Expected: the cropped 5-day chart + caption appears in the channel.

- [ ] **Step 4: Commit**

```bash
git add src/burevestnik/main.py
git commit -m "feat(main): post 5-day outlook on Mon/Thu mornings"
```

---

### Task 7: Document the new behavior

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the architecture + CI notes**

In `CLAUDE.md`, under `## Architecture`, add a short paragraph after the pipeline description:

```markdown
On Monday and Thursday mornings (today-mode runs, gated by `main.should_post_outlook`),
`main()` first posts an extra **5-day outlook**: `scrape.fetch_meteogram` screenshots the
"Hourly weather forecast" meteogram cropped to its top temperature panel, `parse.parse_days`
reads `#day1`…`#day5` into `DaySummary` list, and `caption.render_outlook` renders a compact
one-line-per-day caption. This branch is best-effort (wrapped in try/except) so a meteogram
failure never blocks the normal daily forecast that follows.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: describe Mon/Thu 5-day outlook post"
```

---

## Self-Review

**Spec coverage:**
- Trigger (Mon/Thu, today-mode) → Task 3 (`should_post_outlook`) + Task 6 (wiring). ✓
- Best-effort failure isolation → Task 6 try/except. ✓
- Cropped meteogram image → Task 4 (`fetch_meteogram`, shared `_browser_page`). ✓
- 5-day parse → Task 1 (`parse_days`). ✓
- Caption format (no header, no wind, space-separated, `no rain`, sun hours, daily footer) → Task 2 (`render_outlook`). ✓
- Posts before daily, self-contained fetch → Task 5 (`_post_outlook`) + Task 6. ✓
- Tests: parse_days, render_outlook, should_post_outlook fixture-locked; fetch_meteogram manual → Tasks 1,2,3,4. ✓
- Docs → Task 7. ✓

**Placeholder scan:** none — every step has concrete code, commands, and expected output.

**Type consistency:** `parse_days(html, count=5) -> list[DaySummary]`, `render_outlook(days, now, source_url) -> str`, `should_post_outlook(now) -> bool`, `_post_outlook(token, chat_id, source_url, now) -> None`, `fetch_meteogram(url) -> tuple[str, bytes]` — names and signatures consistent across Tasks 1–7. `_browser_page` used by both `fetch` and `fetch_meteogram`.
