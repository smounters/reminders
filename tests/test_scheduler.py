"""Reminder → APScheduler trigger mapping + next_run sanity checks."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from reminders.models import Reminder, SchedType
from reminders.scheduler import ReminderScheduler, build_triggers


def _reminder(sched_type: SchedType, params: dict, **kw) -> Reminder:
    return Reminder(title="t", sched_type=sched_type, sched_params=params, **kw)


def test_once_trigger_in_future():
    run_at = (datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds")
    r = _reminder(SchedType.ONCE, {"run_at": run_at})
    triggers = build_triggers(r)
    assert len(triggers) == 1
    job_id, trigger = triggers[0]
    assert job_id == r.id
    assert isinstance(trigger, DateTrigger)


def test_once_missing_run_at_yields_no_triggers():
    assert build_triggers(_reminder(SchedType.ONCE, {})) == []


def test_interval_minutes():
    r = _reminder(SchedType.INTERVAL, {"every": 15, "unit": "minutes"})
    triggers = build_triggers(r)
    assert len(triggers) == 1
    job_id, trigger = triggers[0]
    assert job_id == r.id
    assert isinstance(trigger, IntervalTrigger)


def test_interval_hours():
    r = _reminder(SchedType.INTERVAL, {"every": 2, "unit": "hours"})
    triggers = build_triggers(r)
    assert isinstance(triggers[0][1], IntervalTrigger)


def test_interval_zero_is_rejected():
    assert build_triggers(_reminder(SchedType.INTERVAL, {"every": 0})) == []


def test_weekly_single_time_single_job():
    r = _reminder(
        SchedType.WEEKLY,
        {"days": ["mon", "wed", "fri"], "times": ["09:00"]},
    )
    triggers = build_triggers(r)
    assert len(triggers) == 1
    assert isinstance(triggers[0][1], CronTrigger)


def test_weekly_multiple_times_multiple_jobs():
    r = _reminder(
        SchedType.WEEKLY,
        {"days": ["mon"], "times": ["09:00", "18:00"]},
    )
    triggers = build_triggers(r)
    assert len(triggers) == 2
    job_ids = [t[0] for t in triggers]
    assert job_ids == [f"{r.id}#0", f"{r.id}#1"]
    assert all(isinstance(t[1], CronTrigger) for t in triggers)


def test_weekly_legacy_single_time_field():
    r = _reminder(
        SchedType.WEEKLY,
        {"days": ["tue"], "time": "07:30"},
    )
    triggers = build_triggers(r)
    assert len(triggers) == 1


def test_cron_from_crontab():
    r = _reminder(SchedType.CRON, {"expr": "0 * * * *"})
    triggers = build_triggers(r)
    assert len(triggers) == 1
    assert isinstance(triggers[0][1], CronTrigger)


def test_cron_missing_expr():
    assert build_triggers(_reminder(SchedType.CRON, {})) == []


def test_register_yields_next_run():
    fired: list[str] = []
    sched = ReminderScheduler(fired.append)
    sched.start()
    try:
        run_at = (datetime.now() + timedelta(minutes=10)).isoformat(timespec="seconds")
        r = _reminder(SchedType.ONCE, {"run_at": run_at})
        sched.register(r)
        nxt = sched.next_run(r.id)
        assert nxt is not None
        assert nxt > datetime.now().astimezone() - timedelta(seconds=5)
    finally:
        sched.shutdown()


def test_disabled_reminder_is_not_scheduled():
    fired: list[str] = []
    sched = ReminderScheduler(fired.append)
    sched.start()
    try:
        run_at = (datetime.now() + timedelta(minutes=10)).isoformat(timespec="seconds")
        r = _reminder(SchedType.ONCE, {"run_at": run_at}, enabled=False)
        sched.register(r)
        assert sched.next_run(r.id) is None
    finally:
        sched.shutdown()


def test_unregister_removes_all_jobs():
    fired: list[str] = []
    sched = ReminderScheduler(fired.append)
    sched.start()
    try:
        r = _reminder(
            SchedType.WEEKLY,
            {"days": ["mon", "fri"], "times": ["09:00", "18:00"]},
        )
        sched.register(r)
        assert sched.next_run(r.id) is not None
        sched.unregister(r.id)
        assert sched.next_run(r.id) is None
    finally:
        sched.shutdown()


@pytest.mark.parametrize(
    "sched_type,params",
    [
        (SchedType.ONCE, {}),
        (SchedType.INTERVAL, {"every": 0}),
        (SchedType.WEEKLY, {"days": [], "times": ["09:00"]}),
        (SchedType.WEEKLY, {"days": ["mon"], "times": []}),
        (SchedType.CRON, {"expr": ""}),
    ],
)
def test_invalid_configs_produce_no_triggers(sched_type, params):
    assert build_triggers(_reminder(sched_type, params)) == []
