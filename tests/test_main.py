from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from burevestnik.main import should_forecast_tomorrow

_TZ = ZoneInfo("Australia/Melbourne")
_FIXTURE = (Path(__file__).parent / "fixtures" / "meteoblue.html").read_text(encoding="utf-8")


def test_should_forecast_tomorrow_false_at_15_59():
    assert should_forecast_tomorrow(datetime(2026, 5, 10, 15, 59, tzinfo=_TZ)) is False


def test_should_forecast_tomorrow_true_at_16_00_exactly():
    # 16:00:00 is "past 4 PM" colloquially — cutoff fires at the top of the hour.
    assert should_forecast_tomorrow(datetime(2026, 5, 10, 16, 0, tzinfo=_TZ)) is True


def test_should_forecast_tomorrow_true_late_evening():
    assert should_forecast_tomorrow(datetime(2026, 5, 10, 23, 0, tzinfo=_TZ)) is True


def test_should_forecast_tomorrow_false_at_midnight():
    assert should_forecast_tomorrow(datetime(2026, 5, 11, 0, 0, tzinfo=_TZ)) is False


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
