"""One-shot script to capture meteoblue HTML for use as test fixture.

Run: uv run python scripts/capture_fixture.py

Uses the production scrape.fetch() so the captured HTML reflects exactly
what the bot will see in production (units forced to °C / kn / mm,
toggled to 1h view). Re-run any time the layout appears to change, then
update assertions in tests/test_parse.py if values changed.
"""
from pathlib import Path

from burevestnik.scrape import fetch

URL = "https://www.meteoblue.com/en/weather/week/melbourne-cbd_australia_11523810"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "meteoblue.html"


def main() -> None:
    html, _jpeg = fetch(URL)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} ({len(html):,} chars)")


if __name__ == "__main__":
    main()
