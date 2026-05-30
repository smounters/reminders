"""Wrap APScheduler 3.x and map Reminder rows to triggers.

Threading note: APScheduler runs job callbacks on a background worker thread.
GTK and libnotify must not be called from those threads — the dispatcher
delegates to a fire-callback which is expected to marshal to the GLib main
loop via ``GLib.idle_add``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dateutil import parser as date_parser

from reminders.models import Reminder, SchedType

log = logging.getLogger(__name__)

FireCallback = Callable[[str], None]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except (ValueError, TypeError):
        log.warning("Could not parse datetime: %r", value)
        return None


def _parse_hhmm(value: str) -> tuple[int, int]:
    h_str, _, m_str = value.partition(":")
    return int(h_str), int(m_str or 0)


def build_triggers(reminder: Reminder) -> list[tuple[str, object]]:
    """Build (job_id, trigger) pairs. Weekly with multiple times → multiple jobs."""
    p = reminder.sched_params or {}
    t = reminder.sched_type

    if t == SchedType.ONCE:
        run_at = _parse_dt(p.get("run_at"))
        if run_at is None:
            return []
        return [(reminder.id, DateTrigger(run_date=run_at))]

    if t == SchedType.INTERVAL:
        every = int(p.get("every", 0) or 0)
        if every <= 0:
            return []
        unit = p.get("unit", "minutes")
        kwargs: dict[str, object] = {}
        if unit == "hours":
            kwargs["hours"] = every
        else:
            kwargs["minutes"] = every
        start = _parse_dt(p.get("start_at"))
        if start is not None:
            kwargs["start_date"] = start
        return [(reminder.id, IntervalTrigger(**kwargs))]

    if t == SchedType.WEEKLY:
        days = p.get("days") or []
        if not days:
            return []
        times = p.get("times")
        if not times:
            single = p.get("time")
            times = [single] if single else []
        if not times:
            return []
        day_of_week = ",".join(days)
        triggers: list[tuple[str, object]] = []
        for idx, t_str in enumerate(times):
            hour, minute = _parse_hhmm(t_str)
            triggers.append(
                (
                    f"{reminder.id}#{idx}",
                    CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute),
                )
            )
        return triggers

    if t == SchedType.CRON:
        expr = p.get("expr")
        if not expr:
            return []
        return [(reminder.id, CronTrigger.from_crontab(expr))]

    return []


class ReminderScheduler:
    def __init__(self, fire_cb: FireCallback) -> None:
        self.fire_cb = fire_cb
        self.scheduler = BackgroundScheduler()
        # reminder_id → list of APScheduler job_ids.
        self._jobs: dict[str, list[str]] = {}
        self._paused = False

    # ── lifecycle ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start(paused=self._paused)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # ── (un)registering reminders ──────────────────────────────────────────
    def register(self, reminder: Reminder) -> None:
        self.unregister(reminder.id)
        if not reminder.enabled:
            return
        for job_id, trigger in build_triggers(reminder):
            try:
                self.scheduler.add_job(
                    self._dispatch,
                    trigger=trigger,
                    id=job_id,
                    args=[reminder.id],
                    replace_existing=True,
                    misfire_grace_time=60,
                    coalesce=True,
                    max_instances=1,
                )
                self._jobs.setdefault(reminder.id, []).append(job_id)
            except Exception:
                log.exception("Failed to schedule reminder %s", reminder.id)

    def unregister(self, reminder_id: str) -> None:
        for job_id in self._jobs.pop(reminder_id, []):
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                log.debug("remove_job(%s) failed", job_id, exc_info=True)

    def reload(self, reminders: list[Reminder]) -> None:
        for reminder_id in list(self._jobs.keys()):
            self.unregister(reminder_id)
        for r in reminders:
            self.register(r)

    # ── pause/resume ───────────────────────────────────────────────────────
    def pause(self) -> None:
        self._paused = True
        if self.scheduler.running:
            self.scheduler.pause()

    def resume(self) -> None:
        self._paused = False
        if self.scheduler.running:
            self.scheduler.resume()

    @property
    def paused(self) -> bool:
        return self._paused

    # ── inspection ─────────────────────────────────────────────────────────
    def next_run(self, reminder_id: str) -> datetime | None:
        candidates: list[datetime] = []
        for job_id in self._jobs.get(reminder_id, []):
            job = self.scheduler.get_job(job_id)
            if job and job.next_run_time:
                candidates.append(job.next_run_time)
        return min(candidates) if candidates else None

    def next_run_global(self) -> datetime | None:
        candidates = [j.next_run_time for j in self.scheduler.get_jobs() if j.next_run_time]
        return min(candidates) if candidates else None

    # ── dispatcher ─────────────────────────────────────────────────────────
    def _dispatch(self, reminder_id: str) -> None:
        try:
            self.fire_cb(reminder_id)
        except Exception:
            log.exception("Fire callback for %s failed", reminder_id)
