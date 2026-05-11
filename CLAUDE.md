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
main.py  →  scrape.fetch(url)  →  parse.extract(html)  →  caption.render(forecast)  →  telegram.send_photo()
            (Playwright I/O)     (pure, HTML→Forecast)   (pure, Forecast→str)         (httpx POST)
```

Two key invariants make the parser tractable:

1. **`scrape.py` is the only module with browser side effects.** It pre-seeds the `temp` / `speed` / `precip` cookies on `www.meteoblue.com` so the page renders in `CELSIUS / KNOT / MILLIMETER` regardless of the runner's geo-IP — this is what makes `parse.py` regex-based and geo-IP-independent. (Cookie-based unit setting also avoids losing query strings like `?day=2`: meteoblue's settings-menu unit anchors point at the bare base URL, so clicking them in tomorrow-mode would silently revert the page to today.) It then flips the table to the 1-hour view via `label.switch-with-label` and screenshots `table.hourlywind`.

2. **`parse.py` and `caption.py` are pure.** `parse.py` takes HTML strings and returns frozen `DaySummary` / `Forecast` dataclasses (defined in `models.py`); `caption.py` takes a `Forecast` + `datetime` and returns an HTML-formatted Telegram caption string (must stay under 1024 chars — Telegram's caption limit). All parser tests run against `tests/fixtures/meteoblue.html` — no live network in the test suite.

`parse.parse_peak_rain_mm` reads the row of hourly mm values from `table.hourlywind` (`tr.precip`) and returns the highest value with the earliest tie-break; `parse.parse_temp_felt` reads `tr.temperature-felt` from the same table and returns `(max, min)`. Both reflect whichever day the page was fetched for (`?day=2` swaps the table to tomorrow at the scrape layer), so they need no `for_tomorrow` flag.

## CI behavior

The workflow has dual modes: on `push` to master/main it runs only `pytest` (no browser, no posting). On `schedule` or `workflow_dispatch` it skips tests, restores the Playwright browser cache, and runs the full pipeline. Use `workflow_dispatch` for manual end-to-end tests against the real Telegram channel.

The cron in `post.yml` is `17 6/12 * * *` (UTC). This is chosen so the two daily runs land at ~04:17 and ~16:17 Melbourne local time — the morning run posts today's forecast, the afternoon run crosses the 16:00 cutoff and posts tomorrow's. `FORECAST_TZ` shifts the cutoff and the caption stamp but **does not** retime the cron, so overriding it for a non-Australian timezone will desync the morning/evening framing. If you actually want to retarget a different city, change both the cron schedule and `FORECAST_TZ` together.
