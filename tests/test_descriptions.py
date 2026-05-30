"""Human-readable schedule descriptions (Russian)."""

from __future__ import annotations

import pytest

from reminders.models import SchedType, describe_schedule


def test_describe_once_iso():
    text = describe_schedule(SchedType.ONCE, {"run_at": "2026-06-01T09:30:00"})
    assert text == "01.06.2026 09:30"


def test_describe_once_invalid_iso_keeps_raw():
    text = describe_schedule(SchedType.ONCE, {"run_at": "garbage"})
    assert "garbage" in text


def test_describe_once_missing_run_at():
    assert describe_schedule(SchedType.ONCE, {}) == "Однократно"


def test_describe_interval_minutes_plural():
    assert describe_schedule(SchedType.INTERVAL, {"every": 30}) == "Каждые 30 мин"


def test_describe_interval_minute_singular():
    assert describe_schedule(SchedType.INTERVAL, {"every": 1}) == "Каждую минуту"


def test_describe_interval_hour_singular():
    text = describe_schedule(SchedType.INTERVAL, {"every": 1, "unit": "hours"})
    assert text == "Каждый час"


def test_describe_interval_hours_plural():
    text = describe_schedule(SchedType.INTERVAL, {"every": 2, "unit": "hours"})
    assert text == "Каждые 2 ч"


def test_describe_weekly_single_time():
    text = describe_schedule(SchedType.WEEKLY, {"days": ["mon", "wed", "fri"], "times": ["09:00"]})
    assert text == "Пн/Ср/Пт в 09:00"


def test_describe_weekly_multiple_times():
    text = describe_schedule(SchedType.WEEKLY, {"days": ["mon"], "times": ["09:00", "18:00"]})
    assert text == "Пн в 09:00, 18:00"


def test_describe_weekly_legacy_single_time_field():
    text = describe_schedule(SchedType.WEEKLY, {"days": ["tue"], "time": "07:30"})
    assert text == "Вт в 07:30"


def test_describe_cron():
    text = describe_schedule(SchedType.CRON, {"expr": "0 * * * *"})
    assert "0 * * * *" in text


@pytest.mark.parametrize("sched_type", list(SchedType))
def test_describe_does_not_raise_on_empty(sched_type):
    describe_schedule(sched_type, {})
