"""Entry point. Reads env, selects today vs. tomorrow forecast by local hour, posts to Telegram.

Run: uv run python -m burevestnik.main

Env overrides:
  METEOBLUE_URL  — page to scrape (default: Melbourne CBD weekly view)
  FORECAST_TZ    — IANA timezone name (default: Australia/Melbourne) controlling
                   the today/tomorrow cutoff and the "Updated HH:MM TZ" caption line
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from burevestnik import caption, parse, scrape, telegram

DEFAULT_URL = (
    "https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810"
)
DEFAULT_TZ_NAME = "Australia/Melbourne"
TOMORROW_CUTOFF_HOUR = 16  # 16:00 local — runs at/after this post tomorrow's forecast
OUTLOOK_WEEKDAYS = (0, 3)  # Monday, Thursday (datetime.weekday(): Mon=0 … Sun=6)


def should_forecast_tomorrow(now: datetime) -> bool:
    """Return True if the run should post tomorrow's forecast instead of today's.

    Cutoff is 16:00 inclusive in whatever timezone `now` carries (16:00:00 → True,
    15:59:59 → False). Default is Melbourne; `FORECAST_TZ` env can override.
    """
    return now.hour >= TOMORROW_CUTOFF_HOUR


def should_post_outlook(now: datetime) -> bool:
    """Return True on the Monday/Thursday morning (today-mode) runs only.

    The extra 5-day outlook post fires once on those mornings, before the daily
    forecast. The evening runs are tomorrow-mode and are excluded.
    """
    return now.weekday() in OUTLOOK_WEEKDAYS and not should_forecast_tomorrow(now)


def _require_env(name: str) -> str:
    """Read `name` from env; fail loudly if unset OR empty.

    GitHub Actions substitutes a missing repo secret with an empty string
    (not a missing key), so a bare `os.environ[name]` would silently return
    "" and produce a confusing 404 from Telegram. Treat empty as missing.
    """
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(
            f"required environment variable {name!r} is unset or empty. "
            f"In GitHub Actions, add it under Settings → Secrets and variables → Actions."
        )
    return value


def _post_outlook(token: str, chat_id: str, source_url: str, now: datetime) -> None:
    """Post the 5-day outlook photo (cropped meteogram + per-day caption)."""
    html, jpeg = scrape.fetch_meteogram(source_url)
    days = parse.parse_days(html, 5)
    text = caption.render_outlook(days, now, source_url)
    print(f"outlook: {len(days)} days, {len(text)} caption chars")
    telegram.send_photo(token, chat_id, jpeg, text)


def main() -> int:
    print("boot")

    tz = ZoneInfo(os.environ.get("FORECAST_TZ") or DEFAULT_TZ_NAME)
    now = datetime.now(tz)
    for_tomorrow = should_forecast_tomorrow(now)
    print(f"mode: {'tomorrow' if for_tomorrow else 'today'}")

    token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")
    url = os.environ.get("METEOBLUE_URL", DEFAULT_URL)

    # Fetch with ?day=2 in tomorrow-mode so meteoblue renders day-2's
    # hourly table. The unmodified `url` is what we link to in the caption.
    if for_tomorrow:
        sep = "&" if "?" in url else "?"
        fetch_url = f"{url}{sep}day=2"
    else:
        fetch_url = url

    html, jpeg = scrape.fetch(fetch_url)
    print(f"scraped: {len(jpeg):,} jpeg bytes")

    forecast = parse.extract(html, for_tomorrow=for_tomorrow)
    print(
        f"parsed: {forecast.primary.temp_max_c}°/{forecast.primary.temp_min_c}°, "
        f"peak rain {forecast.peak_rain_mm}mm at {forecast.peak_rain_time or 'n/a'}"
    )

    text = caption.render(forecast, now, url, for_tomorrow=for_tomorrow)
    print(f"caption: {len(text)} chars")

    telegram.send_photo(token, chat_id, jpeg, text)
    print("telegram: 200 OK")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
