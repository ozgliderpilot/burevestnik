from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from burevestnik.main import forecast_page_url, should_post_outlook
from burevestnik.models import ForecastDay, ForecastDayKind, forecast_day
from burevestnik.parse import extract

_TZ = ZoneInfo("Australia/Melbourne")
_FIXTURE = (Path(__file__).parent / "fixtures" / "meteoblue.html").read_text(encoding="utf-8")
_SOURCE = "https://example.com/week"


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


def test_forecast_page_url_today_leaves_source_unmodified():
    day = ForecastDay.today(date(2026, 5, 10))
    assert forecast_page_url(_SOURCE, day) == _SOURCE


def test_forecast_page_url_tomorrow_appends_day_query():
    day = ForecastDay.tomorrow(date(2026, 5, 11))
    assert forecast_page_url(_SOURCE, day) == f"{_SOURCE}?day=2"


def test_forecast_page_url_tomorrow_uses_ampersand_when_query_exists():
    day = ForecastDay.tomorrow(date(2026, 5, 11))
    assert forecast_page_url(f"{_SOURCE}?x=1", day) == f"{_SOURCE}?x=1&day=2"


def test_page_url_and_extract_share_the_same_forecast_day():
    # The missing wiring test: URL shaping and extract receive one Forecast day.
    now = datetime(2026, 5, 10, 18, 0, tzinfo=_TZ)
    day = forecast_day(now)
    assert day.kind is ForecastDayKind.TOMORROW
    assert forecast_page_url(_SOURCE, day) == f"{_SOURCE}?day={day.page_index}"
    forecast = extract(_FIXTURE, day=day)
    assert forecast.day == day
    assert forecast.next_day_preview is None
    assert forecast.primary.label == "Tomorrow"


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


def test_main_continues_to_daily_when_outlook_fails(monkeypatch):
    # The outlook branch is best-effort: if _post_outlook raises, main() must
    # swallow it and still post the daily forecast (the core product).
    from burevestnik import main, scrape, telegram

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@chan")
    monkeypatch.setattr(main, "should_post_outlook", lambda now: True)

    def boom(*args, **kwargs):
        raise RuntimeError("meteogram boom")

    monkeypatch.setattr(main, "_post_outlook", boom)

    sent = []
    monkeypatch.setattr(scrape, "fetch", lambda url: (_FIXTURE, b"daily-jpeg"))
    monkeypatch.setattr(telegram, "send_photo", lambda *a, **k: sent.append(a))

    rc = main.main()

    assert rc == 0
    # The outlook send never happened (it raised); only the daily post did.
    assert len(sent) == 1
    assert sent[0][2] == b"daily-jpeg"  # image arg of the daily send_photo
