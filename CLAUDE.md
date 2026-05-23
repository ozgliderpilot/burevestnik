# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Telegram bot that scrapes a meteoblue weather page for Melbourne CBD, screenshots the hourly table, and posts a captioned image to a Telegram channel. Runs on a GitHub Actions cron (`.github/workflows/post.yml`) every 12 hours.

## Commands

Dependencies are managed with `uv` (lockfile is `uv.lock`):

```powershell
uv sync --extra dev --frozen        # install runtime + dev deps from lockfile
uv run playwright install chromium  # one-time browser install (CI caches ~/.cache/ms-playwright)
uv run python -m burevestnik.main   # run end-to-end (requires TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID env)
uv run pytest                       # run all tests
uv run pytest tests/test_parse.py::test_parse_day_today_extracts_temps  # single test
```

Required env vars at runtime: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Optional overrides: `METEOBLUE_URL` (defaults to Melbourne CBD weekly view) and `FORECAST_TZ` (IANA timezone name, defaults to `Australia/Melbourne`; controls the today/tomorrow cutoff and the "Updated HH:MM TZ" caption stamp — lat/lon for sunrise/sunset stay hardcoded). Empty strings count as missing — `_require_env` deliberately treats `""` as unset because GitHub Actions substitutes missing repo secrets with empty strings, which would otherwise produce a confusing 404 from Telegram.

## Architecture

The pipeline is a strict 4-stage flow with side effects pushed to the edges:

```
main.py  →  scrape.fetch(url)         →  parse.extract(html, for_tomorrow=…)  →  caption.render(forecast, now, url, for_tomorrow=…)  →  telegram.send_photo()
            (Playwright I/O,             (pure, HTML→Forecast)                    (pure, Forecast→HTML-formatted str)                      (httpx POST,
             returns html + jpeg)                                                                                                            HTML parse_mode)
```

`main.py` decides today- vs. tomorrow-mode from the current local hour (cutoff 16:00 in `FORECAST_TZ`), appends `?day=2` to the URL it hands to `scrape.fetch` in tomorrow-mode (the unmodified URL is what the caption links to), and threads `for_tomorrow` through `parse.extract` and `caption.render`. `scrape.py` itself is URL-agnostic — it opens whatever it's given.

Two key invariants make the parser tractable:

1. **`scrape.py` is the only module with browser side effects.** It pre-seeds the `temp` / `speed` / `precip` cookies on `www.meteoblue.com` so the page renders in `CELSIUS / KNOT / MILLIMETER` regardless of the runner's geo-IP — this is what makes `parse.py` regex-based and geo-IP-independent. (Cookie-based unit setting also avoids losing query strings like `?day=2`: meteoblue's settings-menu unit anchors point at the bare base URL, so clicking them in tomorrow-mode would silently revert the page to today.) It then dismisses the GDPR overlay, flips the table to the 1-hour view via `label.switch-with-label`, and screenshots `table.hourlywind`.

2. **`parse.py` and `caption.py` are pure.** `parse.py` takes HTML strings and returns frozen `DaySummary` / `Forecast` dataclasses (defined in `models.py`); `caption.py` takes a `Forecast` + `datetime` + source URL and returns an HTML-formatted Telegram caption string (must stay under 1024 chars — Telegram's caption limit; `parse_mode=HTML` in `telegram.send_photo`). All parser tests run against `tests/fixtures/meteoblue.html` — no live network in the test suite.

`Forecast` carries the displayed day's summary plus hourly-table-derived metrics: peak rain (mm + `HH:00`), felt temp range, wind range, peak gust, UV index, and sunrise/sunset. Each is extracted by a dedicated `parse_*` helper that reads one row of `table.hourlywind` (or a sibling page-level block for UV / sun times). They reflect whichever day the page was fetched for — `?day=2` swaps the table to tomorrow at the URL level — so they need no `for_tomorrow` flag. In tomorrow-mode the `next_day_preview` field is `None` (no day-after teaser at end-of-day).

Each `DaySummary` also carries `condition` — meteoblue's day-pictogram `alt` text (e.g. `"Partly cloudy"`, `"Overcast with rain"`) read from `.weather-pictogram-wrapper.day img.weather-pictogram` inside the `#dayN` tab. `caption._condition_emoji` maps it to the headline emoji via priority-ordered keyword rules (thunder > snow > fog > rain > clouds > clear), with light/occasional rain split off as 🌦 vs heavy 🌧. Unknown or missing labels fall back to 🌦, so the caption can't be broken by a meteoblue label we haven't seen. The caption omits the city name (the channel name covers it) and runs the headline directly into the felt-temp line so the iPhone push-notification preview shows both at a glance.

## CI behavior

The workflow has dual modes: on `push` to master/main it runs only `pytest` (no browser, no posting). On `schedule` or `workflow_dispatch` it skips tests, restores the Playwright browser cache, and runs the full pipeline. Use `workflow_dispatch` for manual end-to-end tests against the real Telegram channel.

The cron in `post.yml` is `17 6/12 * * *` (UTC). This is chosen so the two daily runs land at ~04:17 and ~16:17 Melbourne local time — the morning run posts today's forecast, the afternoon run crosses the 16:00 cutoff and posts tomorrow's. `FORECAST_TZ` shifts the cutoff and the caption stamp but **does not** retime the cron, so overriding it for a non-Australian timezone will desync the morning/evening framing. If you actually want to retarget a different city, change both the cron schedule and `FORECAST_TZ` together.
