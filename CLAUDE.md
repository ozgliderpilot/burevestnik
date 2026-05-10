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

Required env vars at runtime: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Optional override: `METEOBLUE_URL` (defaults to Melbourne CBD weekly view). Empty strings count as missing — `_require_env` deliberately treats `""` as unset because GitHub Actions substitutes missing repo secrets with empty strings, which would otherwise produce a confusing 404 from Telegram.

## Architecture

The pipeline is a strict 4-stage flow with side effects pushed to the edges:

```
main.py  →  scrape.fetch(url)  →  parse.extract(html)  →  caption.render(forecast)  →  telegram.send_photo()
            (Playwright I/O)     (pure, HTML→Forecast)   (pure, Forecast→str)         (httpx POST)
```

Two key invariants make the parser tractable:

1. **`scrape.py` is the only module with browser side effects.** It clicks through the meteoblue settings menu to force `CELSIUS / KNOT / MILLIMETER` units before extracting HTML — this is what makes `parse.py` regex-based and geo-IP-independent. Each unit click navigates back to the same URL, so the GDPR consent banner has to be re-dismissed after every click (`_dismiss_banner` is called in a loop). It also flips the table to the 1-hour view via `label.switch-with-label` and screenshots `table.hourlywind`.

2. **`parse.py` and `caption.py` are pure.** `parse.py` takes HTML strings and returns frozen `DaySummary` / `Forecast` dataclasses (defined in `models.py`); `caption.py` takes a `Forecast` + `datetime` and returns an HTML-formatted Telegram caption string (must stay under 1024 chars — Telegram's caption limit). All parser tests run against `tests/fixtures/meteoblue.html` — no live network in the test suite.

`parse.parse_peak_rain` finds the row in `table.hourlywind` whose cells are ≥60% percentages, then picks the highest `%` and the earliest hour on ties. If meteoblue ever changes the layout enough that the rain-mm span vanishes but the percent row remains, the caption will surface this as `0mm alongside Peak N%` — that's the diagnostic signal, not a bug.

## CI behavior

The workflow has dual modes: on `push` to master/main it runs only `pytest` (no browser, no posting). On `schedule` or `workflow_dispatch` it skips tests, restores the Playwright browser cache, and runs the full pipeline. Use `workflow_dispatch` for manual end-to-end tests against the real Telegram channel.
