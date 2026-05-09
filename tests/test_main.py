from datetime import datetime
from zoneinfo import ZoneInfo
from burevestnik.main import should_post

_TZ = ZoneInfo("Australia/Melbourne")


def test_should_post_on_schedule_during_posting_hour():
    decision, _ = should_post(datetime(2026, 5, 3, 15, 0, tzinfo=_TZ), "schedule")
    assert decision is True

def test_should_post_bypasses_gate_at_midnight_too():
    decision, _ = should_post(datetime(2026, 5, 3, 0, 0, tzinfo=_TZ), "workflow_dispatch")
    assert decision is True
