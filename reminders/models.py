"""Data model for a reminder and helpers for serializing schedule params."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SchedType(str, Enum):
    ONCE = "once"
    INTERVAL = "interval"
    WEEKLY = "weekly"
    CRON = "cron"


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_WEEKDAYS_RU = {
    "mon": "Пн",
    "tue": "Вт",
    "wed": "Ср",
    "thu": "Чт",
    "fri": "Пт",
    "sat": "Сб",
    "sun": "Вс",
}


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


@dataclass
class Reminder:
    """A single user reminder.

    ``sched_params`` is a JSON-serializable dict. Its schema depends on
    ``sched_type``:

    * ``once``     – ``{"run_at": "ISO8601 local"}``
    * ``interval`` – ``{"every": int, "unit": "minutes"|"hours", "start_at": "ISO"|None}``
    * ``weekly``   – ``{"days": ["mon", ...], "times": ["HH:MM", ...]}``
    * ``cron``     – ``{"expr": "* * * * *"}``
    """

    title: str
    message: str = ""
    enabled: bool = True
    sound: bool = True
    sched_type: SchedType = SchedType.ONCE
    sched_params: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Reminder:
        return cls(
            id=row["id"],
            title=row["title"],
            message=row["message"] or "",
            enabled=bool(row["enabled"]),
            sound=bool(row["sound"]),
            sched_type=SchedType(row["sched_type"]),
            sched_params=json.loads(row["sched_params"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "enabled": 1 if self.enabled else 0,
            "sound": 1 if self.sound else 0,
            "sched_type": self.sched_type.value,
            "sched_params": json.dumps(self.sched_params, ensure_ascii=False),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def describe_schedule(sched_type: SchedType, params: dict[str, Any]) -> str:
    """Human-readable schedule description in Russian."""
    if sched_type == SchedType.ONCE:
        run_at = params.get("run_at")
        if not run_at:
            return "Однократно"
        try:
            dt = datetime.fromisoformat(run_at)
            return dt.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return f"Однократно: {run_at}"

    if sched_type == SchedType.INTERVAL:
        every = int(params.get("every", 0) or 0)
        unit = params.get("unit", "minutes")
        if unit == "hours":
            if every == 1:
                return "Каждый час"
            return f"Каждые {every} ч"
        if every == 1:
            return "Каждую минуту"
        return f"Каждые {every} мин"

    if sched_type == SchedType.WEEKLY:
        days = params.get("days") or []
        times = params.get("times")
        if not times:
            single = params.get("time")
            times = [single] if single else []
        days_str = "/".join(_WEEKDAYS_RU.get(d, d) for d in days) or "—"
        times_str = ", ".join(times) or "—"
        return f"{days_str} в {times_str}"

    if sched_type == SchedType.CRON:
        return f"cron: {params.get('expr', '')}"

    return "—"
