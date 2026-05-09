# Burevestnik — Design Doc

**Date:** 2026-05-03
**Status:** Brainstorming complete, awaiting user review before implementation plan
**Project:** Telegram bot that posts a meteoblue 1-hourly weather forecast for North Melbourne to a private channel, 5x daily.

---

## 1. Goals & Scope

**Build:** a small Python program that:
1. Scrapes the meteoblue weekly forecast page for North Melbourne.
2. Toggles the page's "3h / 1h" switch to the **1-hour** granularity.
3. Screenshots the resulting `table.hourlywind` element as JPEG.
4. Parses summary data (today, tomorrow, peak rain, sun hours) from the rendered DOM.
5. Computes sunrise/sunset astronomically.
6. Posts the JPEG plus a rich text caption to a Telegram channel.
7. Runs from GitHub Actions cron, 5 times per Melbourne day: 06:00, 09:00, 12:00, 15:00, 18:00.

**Non-goals (v1):** caching, retries, dedup, multi-location, mobile UX, configurable schedule, alerting on weather thresholds.

**URL:** `https://www.meteoblue.com/en/weather/week/north-melbourne_australia_2154912`

---

## 2. Architecture

```
GitHub Actions (cron: every UTC hour)
  └─ runs Python entrypoint
       └─ main.py orchestrates:
            ┌────────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
            │  scrape.py │───▶│ parse.py │───▶│caption.py│───▶│telegram.py │
            │ (Playwright│    │  (pure)  │    │  (pure)  │    │ (POST API) │
            │  + JPEG)   │    │          │    │ +astral  │    │            │
            └────────────┘    └──────────┘    └──────────┘    └────────────┘
                  ▲                                                  │
                  │                                                  ▼
            meteoblue.com                                     Telegram channel
                                                               (private, by ID)
```

**Single end-to-end run per cron firing.** No persistent state, no DB, no cache between runs. The workflow runs every UTC hour, but `main.py` exits early if the current Melbourne local hour is not in `{6, 9, 12, 15, 18}`. This is how DST-correct scheduling is achieved without recomputing UTC cron expressions twice a year.

**Total LoC budget:** ~250 across 5 Python files plus 1 GitHub Actions YAML.

---

## 3. File Layout

```
burevestnik/
├── pyproject.toml                      # uv project, deps pinned via uv.lock
├── uv.lock
├── README.md                           # bot/channel setup steps (see §7)
├── .github/
│   └── workflows/
│       └── post.yml                    # cron + secrets + Playwright install
├── src/burevestnik/
│   ├── __init__.py
│   ├── main.py                         # entrypoint: orchestration + DST gate
│   ├── scrape.py                       # Playwright I/O
│   ├── parse.py                        # pure HTML → typed dataclasses
│   ├── caption.py                      # pure dataclasses → caption string
│   └── telegram.py                     # POST sendPhoto
└── tests/
    ├── fixtures/
    │   ├── meteoblue_2026-05-03.html   # captured page after 1h toggle
    │   └── meteoblue_no-rain.html      # edited variant for zero-rain edge case
    ├── test_parse.py
    └── test_caption.py
```

---

## 4. Components

### 4.1 Module responsibilities

| Module | Inputs | Outputs | Side effects |
|---|---|---|---|
| `scrape.py` | `url: str` | `(rendered_html: str, screenshot_jpeg: bytes)` | Network: Chromium launch, navigate, dismiss cookie banner, click `label.switch-with-label` to toggle 1h, screenshot `table.hourlywind` |
| `parse.py` | `html: str` | `Forecast` dataclass | None (pure) |
| `caption.py` | `Forecast`, `dt: datetime` | `caption: str` | None (pure; uses `astral` to compute sunrise/sunset) |
| `telegram.py` | `bot_token`, `chat_id`, `image: bytes`, `caption: str` | None (raises on non-2xx) | Network: one `POST /sendPhoto` |
| `main.py` | env vars | exit code | Reads env, gates on Melbourne hour, calls others, fails loud |

### 4.2 Dataclasses

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
    peak_rain_time: str         # "12:00" — the slot where peak hit
```

### 4.3 Dependencies (pinned via `pyproject.toml` + `uv.lock`)

- `playwright` — browser automation
- `httpx` — Telegram API call (avoids `python-telegram-bot`'s heavyweight async runtime; one POST is all we need)
- `astral` — sunrise/sunset
- `selectolax` — fast HTML parsing for `parse.py`
- dev: `pytest`

**Python version:** 3.12 (matches GH Actions default Python).

---

## 5. Data Flow (one cron firing)

```
[GH Actions cron: 5 * * * *]   (every UTC hour, at :05)
        │
        ▼
[1] main.py boot
    - read env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    - now_melb = datetime.now(ZoneInfo("Australia/Melbourne"))
    - if now_melb.hour not in {6, 9, 12, 15, 18}:
          print("not a posting hour"); exit 0
        │
        ▼
[2] scrape.fetch(url) → (html, jpeg_bytes)
    - launch Chromium (Playwright sync API, headless, viewport 1280×900)
    - goto(url, wait_until="networkidle")
    - remove `.fc-consent-root` (cookie banner) via page.evaluate
    - click `label.switch-with-label` (toggles 3h → 1h)
    - wait for `table.hourlywind` to be visible (timeout 5s)
    - html = page.content()
    - jpeg_bytes = page.locator("table.hourlywind")
                       .screenshot(type="jpeg", quality=90)
    - browser.close()
        │
        ▼
[3] parse.extract(html) → Forecast
    - selectolax parses html
    - today    = parse_day(doc, "#day1")
    - tomorrow = parse_day(doc, "#day2")
    - peak_rain_pct, peak_rain_time = parse_peak_rain(doc, "table.hourlywind")
        # Tie-breaking: if multiple hours share the max %, return the
        # earliest hour (so the user is alerted to the start of the peak).
    - return Forecast(...)
        │
        ▼
[4] caption.render(forecast, now_melb) → str
    - astral.sun.sun(LocationInfo("Melbourne", "Australia",
                                  "Australia/Melbourne", -37.81, 144.96),
                     date=now_melb.date(),
                     tzinfo=ZoneInfo("Australia/Melbourne"))
    - returns multi-line HTML-formatted string (see §6)
        │
        ▼
[5] telegram.send_photo(token, chat_id, jpeg_bytes, caption)
    - httpx.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                 data={"chat_id": chat_id, "caption": caption,
                       "parse_mode": "HTML"},
                 files={"photo": ("forecast.jpg", jpeg_bytes, "image/jpeg")},
                 timeout=30)
    - response.raise_for_status()
        │
        ▼
[6] exit 0
```

**Skip behavior:** Steps 2–5 are skipped on hours that aren't 6/9/12/15/18 Melbourne. The job still "runs" hourly so GH Actions never disables it for inactivity, and the early exit takes <2 seconds.

**Active-run wall time:** ~15–25s, dominated by Playwright cold start.

---

## 6. Caption Format

Telegram captions are limited to **1024 characters**. We use `parse_mode=HTML` (simpler escape rules than Markdown).

### 6.1 Template

Placeholder names in the template below use the **exact dataclass field names** from §4.2.

```
🌦 <b>North Melbourne</b> · {weekday_long}, {date}

🌡 High <b>{today.temp_max_c}°</b> / Low {today.temp_min_c}°
☔ Rain {today.rain_mm_low}–{today.rain_mm_high}mm · Peak <b>{forecast.peak_rain_pct}%</b> at {forecast.peak_rain_time}
💨 Wind up to {today.wind_kmh_max}km/h
☀ Sun {today.sun_hours}h · 🌅 {sunrise} · 🌇 {sunset}

<i>Tomorrow:</i> {tomorrow.temp_max_c}°/{tomorrow.temp_min_c}° · {tomorrow.rain_mm_low}–{tomorrow.rain_mm_high}mm · wind {tomorrow.wind_kmh_max}km/h

<i>Updated {hh}:{mm} {tz_abbrev}</i>
```

### 6.2 Rendered example

Using values observed on the page on 2026-05-03 (illustrative; sunrise/sunset times shown are approximate placeholders).

```
🌦 North Melbourne · Sunday, 3 May

🌡 High 21° / Low 15°
☔ Rain 10–20mm · Peak 88% at 12:00
💨 Wind up to 19km/h
☀ Sun 2h · 🌅 06:54 · 🌇 17:33

Tomorrow: 17°/13° · 0–2mm · wind 22km/h

Updated 14:32 AEST
```

### 6.3 Edge cases & formatting rules

- If `today.rain_mm_low == today.rain_mm_high` (e.g. "5mm" not "0–5mm"), collapse the range to a single value.
- If `forecast.peak_rain_pct == 0` across all 24 hours, drop the entire ☔ line.
- If sunrise/sunset are unavailable (`astral` returns `None`, e.g. polar regions), drop the ☀ line. Melbourne never hits this case in practice.
- `tz_abbrev` is "AEST" or "AEDT", taken from `now_melb.strftime("%Z")`.

**Display rounding** (applied at render time; dataclasses keep raw values):
- Temperatures (`temp_max_c`, `temp_min_c`): rounded to integer °C.
- Wind (`wind_kmh_max`): rounded to integer km/h.
- Rain probability (`peak_rain_pct`): integer %.
- Rain mm (`rain_mm_low`, `rain_mm_high`): rounded to integer mm (e.g. `10.4` → `10`).
- Sun hours (`sun_hours`): rounded to integer h (e.g. `2.3` → `2`).
- Sunrise/sunset times: `HH:MM` 24-hour format in Melbourne local time.

---

## 7. Configuration & Secrets

### 7.1 Environment variables

| Var | Source | Example |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | GitHub Actions secret | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | GitHub Actions secret | `-1001234567890` (private channels: negative ints starting `-100`) |
| `METEOBLUE_URL` | hardcoded default in code, overridable via env | `https://www.meteoblue.com/en/weather/week/north-melbourne_australia_2154912` |

### 7.2 First-time bot/channel setup

User has nothing yet. The README will document:

1. Open `@BotFather` in Telegram → `/newbot` → choose name + username → **save the token**.
2. Create a new private channel in Telegram (Settings → New Channel → Private).
3. In the channel: settings → Administrators → Add admin → search the bot's username → grant **Post Messages** permission only.
4. Post any message in the channel from your own account.
5. Forward that message to `@RawDataBot` or `@JsonDumpBot` → it returns the channel's `chat.id` as a negative integer (e.g. `-1001234567890`). **Save it.**
6. In the GitHub repo: Settings → Secrets and variables → Actions → New repository secret. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

---

## 8. Error Handling

**Policy: fail loud, no retries, no caching/fallback for v1.**

| Failure | Behavior | Reasoning |
|---|---|---|
| Network/timeout reaching meteoblue | Raise → workflow fails → GitHub emails owner | Next scheduled run tries fresh in ≤3h |
| Cookie banner removal fails | Continue anyway — banner is cosmetic, table screenshot bypasses it | Don't block on cosmetics |
| Toggle click finds no element OR `table.hourlywind` doesn't appear in 5s | Raise — meteoblue may have changed their layout | Loud signal that maintenance is needed |
| Parsing returns missing fields (e.g. tomorrow tab empty) | Raise — same reason | |
| Telegram API returns 4xx (bad token, bot not admin, channel not found) | Raise — config issue | |
| Telegram API returns 5xx | Raise — try again next run | Only ~3h delay; not worth retry logic |

**Logging:** plain `print()` to stdout — GH Actions captures it. Lines:
- `boot`
- `Melbourne hour: 14 — posting` / `Melbourne hour: 11 — skipping`
- `scraped 24 hourly slots`
- `caption: 421 chars`
- `telegram: 200 OK`
- `done`

---

## 9. Testing Strategy

Intentionally small. The high-risk surface is HTML parsing (meteoblue may change their layout); everything else is either pure or trivial.

### 9.1 Test files

```
tests/
├── fixtures/
│   ├── meteoblue_2026-05-03.html      # full page after 1h toggle, real captured HTML
│   └── meteoblue_no-rain.html         # edited variant for the zero-peak edge case
├── test_parse.py
└── test_caption.py
```

### 9.2 `test_parse.py` (pure, fast, no browser)

- `test_parse_today_extracts_max_min` — load fixture, assert `forecast.today.temp_max_c == 21`, `temp_min_c == 15`
- `test_parse_tomorrow_extracts_brief` — assert `forecast.tomorrow.temp_max_c == 17`
- `test_parse_peak_rain_returns_max_pct_and_hour` — assert `peak_rain_pct` and `peak_rain_time` match the captured fixture's actual peak.
- `test_parse_peak_rain_breaks_ties_to_earliest` — fixture with two hours sharing the max % → returns the earlier hour.
- `test_parse_handles_missing_rain_data` — fixture with all-zero rain row → returns `peak_rain_pct == 0`

### 9.3 `test_caption.py` (pure)

- `test_caption_renders_full_template` — feed dataclass with known values + fixed datetime → assert exact string match
- `test_caption_collapses_equal_rain_range` — `rain_low == rain_high` → no en-dash
- `test_caption_drops_rain_line_when_zero_peak` — `peak_pct == 0` → no ☔ line
- `test_caption_under_1024_chars` — assert always within Telegram's caption limit

### 9.4 Not tested in v1 (intentional scope cap)

- `scrape.py` — requires a live browser; trust Playwright + manual smoke after deploy
- `telegram.py` — single `httpx.post`, trivial
- DST gating in `main.py` — covered by manual run + always-hourly cron

### 9.5 Running

`uv run pytest`. CI runs them on each push to `main`.

---

## 10. GitHub Actions Workflow

`.github/workflows/post.yml`:

```yaml
name: Post weather to Telegram
on:
  schedule:
    - cron: '5 * * * *'    # every UTC hour at :05 (offset from top-of-hour traffic spike); main.py gates on Melbourne local hour
  workflow_dispatch: {}    # manual trigger for testing
  push:
    branches: [main]       # CI test on push (skip cron logic via event check)

jobs:
  post:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install uv && uv sync --frozen
      - run: uv run playwright install --with-deps chromium
      - if: github.event_name == 'push'
        run: uv run pytest
      - if: github.event_name != 'push'
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: uv run python -m burevestnik.main
```

**Cost check:** GH Actions free tier = 2000 min/mo for private repos. Hourly runs × 24 × 30 = 720 runs/mo, averaging ~30s each (most are early-exit skips) ≈ 6h/mo. Comfortably free.

**Caveats acknowledged:**
- GH Actions cron does not auto-handle DST; we sidestep this by running hourly and gating on Melbourne local time inside `main.py`.
- Scheduled runs may be delayed under high platform load (5–15 min). Acceptable for a weather notifier.

---

## 11. Open Questions / Future Work

Out of scope for v1, but worth noting:

- **Switch to meteoblue's JSON API** instead of scraping + screenshot. Tradeoffs:
  - Pros: no Playwright/Chromium dependency (fastest path: ~3s vs ~25s, smaller GH Actions footprint); no risk of breaking when meteoblue changes DOM/CSS; structured data unlocks richer captions (per-hour text summary, weekly trends, alerts).
  - Cons: requires an API key (free tier exists for non-commercial use, but adds a secret + rate-limit awareness); we lose the *visual* table the user already likes — to keep the image, we'd have to render our own chart (matplotlib/Pillow) from the JSON, which is meaningfully more code than `page.screenshot()`.
  - Migration path: keep `parse.py` and `caption.py` interfaces stable; replace `scrape.py` with an `api.py` module that fetches `https://my.meteoblue.com/packages/basic-1h_basic-day` and maps the response into the same `Forecast` dataclass. Tests against fixture HTML get replaced by tests against fixture JSON.
  - Decision deferred to v2 — revisit if (a) meteoblue's HTML breaks parser more than ~once a year, or (b) we want chart styling that the meteoblue site doesn't provide.
- **Caching / last-known-good fallback** if meteoblue returns errors for many runs in a row.
- **Deduplication** — only post if the forecast meaningfully changed since last run.
- **Configurable location** — currently hardcoded to North Melbourne lat/lon and URL.
- **Failure notification** — currently relies on the GitHub Actions failure email; could post to a separate Telegram channel.
- **Schedule tuning** — easier to revisit after observing real-world usefulness of each post.
