"""Entry point. Reads env, gates on Melbourne local hour, posts to Telegram.

Run: uv run python -m burevestnik.main
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from burevestnik import caption, parse, scrape, telegram

MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")
DEFAULT_URL = (
    "https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810"
)

def should_post(now: datetime, event: str) -> tuple[bool, str]:
    return True, f"Melbourne hour: {now.hour} — posting"

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


def main() -> int:
    print("boot")

    now = datetime.now(MELBOURNE_TZ)
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    decision, message = should_post(now, event)
    print(message)
    if not decision:
        return 0

    token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")
    url = os.environ.get("METEOBLUE_URL", DEFAULT_URL)

    html, jpeg = scrape.fetch(url)
    print(f"scraped: {len(jpeg):,} jpeg bytes")

    forecast = parse.extract(html)
    print(
        f"parsed: today {forecast.today.temp_max_c}°/{forecast.today.temp_min_c}°, "
        f"peak rain {forecast.peak_rain_pct}% at {forecast.peak_rain_time or 'n/a'}"
    )

    text = caption.render(forecast, now, url)
    print(f"caption: {len(text)} chars")

    telegram.send_photo(token, chat_id, jpeg, text)
    print("telegram: 200 OK")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
