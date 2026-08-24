"""Entry point. Reads env, selects Forecast day by local hour, posts to Telegram.

Run: uv run python -m burevestnik.main

Env overrides:
  METEOBLUE_URL  — page to scrape (default: Melbourne CBD weekly view)
  FORECAST_TZ    — IANA timezone name (default: Australia/Melbourne) controlling
                   the Forecast-day cutoff and the "Updated HH:MM TZ" caption line
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from burevestnik import caption, parse, scrape, telegram
from burevestnik.models import ForecastDay, ForecastDayKind, forecast_day

DEFAULT_URL = (
    "https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810"
)
DEFAULT_TZ_NAME = "Australia/Melbourne"
OUTLOOK_WEEKDAYS = (0, 3)  # Monday, Thursday (datetime.weekday(): Mon=0 … Sun=6)


def should_post_outlook(now: datetime) -> bool:
    """Return True on the Monday/Thursday morning (Forecast day is Today) runs only.

    The extra 5-day outlook post fires once on those mornings, before the daily
    forecast. Evening runs (Forecast day is Tomorrow) are excluded.
    """
    return (
        now.weekday() in OUTLOOK_WEEKDAYS
        and forecast_day(now).kind is ForecastDayKind.TODAY
    )


def forecast_page_url(source_url: str, day: ForecastDay) -> str:
    """URL scrape.fetch should open for this Forecast day.

    Today uses the source URL unchanged (that's also the caption link).
    Tomorrow appends `?day=N` so meteoblue swaps the hourly table.
    """
    if day.page_index == 1:
        return source_url
    sep = "&" if "?" in source_url else "?"
    return f"{source_url}{sep}day={day.page_index}"


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
    day = forecast_day(now)
    print(f"forecast day: {day.kind.value} {day.date.isoformat()}")

    token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")
    url = os.environ.get("METEOBLUE_URL", DEFAULT_URL)

    # Mon/Thu mornings: post the 5-day outlook first. Best-effort — a failure
    # here (e.g. the meteogram not rendering) must never block the daily post.
    if should_post_outlook(now):
        print("outlook: posting 5-day overview")
        try:
            _post_outlook(token, chat_id, url, now)
            print("outlook: 200 OK")
        except Exception as exc:  # noqa: BLE001 — deliberately broad; daily post must proceed
            print(f"WARNING: outlook post failed, continuing to daily: {exc!r}")

    # The unmodified `url` is what we link to in the caption; scrape.fetch
    # opens the Forecast-day URL (Today: unchanged; Tomorrow: ?day=2).
    html, jpeg = scrape.fetch(forecast_page_url(url, day))
    print(f"scraped: {len(jpeg):,} jpeg bytes")

    forecast = parse.extract(html, day=day)
    print(
        f"parsed: {forecast.primary.temp_max_c}°/{forecast.primary.temp_min_c}°, "
        f"peak rain {forecast.peak_rain_mm}mm at {forecast.peak_rain_time or 'n/a'}"
    )

    text = caption.render(forecast, now, url)
    print(f"caption: {len(text)} chars")

    telegram.send_photo(token, chat_id, jpeg, text)
    print("telegram: 200 OK")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
