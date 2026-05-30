"""Create/edit reminder dialog with Gtk.StackSwitcher per schedule type."""

from __future__ import annotations

import logging
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from reminders.models import WEEKDAYS, Reminder, SchedType

log = logging.getLogger(__name__)


_STACK_NAMES = {
    SchedType.ONCE: "once",
    SchedType.INTERVAL: "interval",
    SchedType.WEEKLY: "weekly",
    SchedType.CRON: "cron",
}
_STACK_TITLES = {
    "once": "Один раз",
    "interval": "Каждые N",
    "weekly": "По дням недели",
    "cron": "Cron",
}
_WEEKDAYS_LABELS = {
    "mon": "Пн",
    "tue": "Вт",
    "wed": "Ср",
    "thu": "Чт",
    "fri": "Пт",
    "sat": "Сб",
    "sun": "Вс",
}


class EditDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window | None, reminder: Reminder | None) -> None:
        super().__init__(
            title="Изменить напоминание" if reminder else "Новое напоминание",
            transient_for=parent,
            flags=0,
        )
        self.set_default_size(540, 520)
        self.add_buttons(
            "_Отмена",
            Gtk.ResponseType.CANCEL,
            "_Сохранить",
            Gtk.ResponseType.OK,
        )
        self.set_default_response(Gtk.ResponseType.OK)

        self._reminder = reminder
        existing_params = reminder.sched_params if reminder else {}
        existing_type = reminder.sched_type if reminder else SchedType.ONCE

        content = self.get_content_area()
        content.set_border_width(12)
        content.set_spacing(8)

        # Title / message
        content.pack_start(self._labeled("Заголовок"), False, False, 0)
        self.entry_title = Gtk.Entry()
        if reminder:
            self.entry_title.set_text(reminder.title)
        content.pack_start(self.entry_title, False, False, 0)

        content.pack_start(self._labeled("Текст"), False, False, 0)
        self.entry_message = Gtk.Entry()
        if reminder:
            self.entry_message.set_text(reminder.message)
        content.pack_start(self.entry_message, False, False, 0)

        # Flags row
        flags_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.chk_sound = Gtk.CheckButton(label="Звук")
        self.chk_sound.set_active(reminder.sound if reminder else True)
        self.chk_enabled = Gtk.CheckButton(label="Включено")
        self.chk_enabled.set_active(reminder.enabled if reminder else True)
        flags_row.pack_start(self.chk_sound, False, False, 0)
        flags_row.pack_start(self.chk_enabled, False, False, 0)
        content.pack_start(flags_row, False, False, 0)

        # Schedule stack
        content.pack_start(self._labeled("Тип расписания"), False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.switcher = Gtk.StackSwitcher()
        self.switcher.set_stack(self.stack)
        content.pack_start(self.switcher, False, False, 0)
        content.pack_start(self.stack, True, True, 0)

        self._build_once_page(existing_type, existing_params)
        self._build_interval_page(existing_type, existing_params)
        self._build_weekly_page(existing_type, existing_params)
        self._build_cron_page(existing_type, existing_params)

        self.stack.set_visible_child_name(_STACK_NAMES[existing_type])

        self.show_all()

    # ── builders ──────────────────────────────────────────────────────────
    @staticmethod
    def _labeled(text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, xalign=0.0)
        return lbl

    def _build_once_page(self, current_type: SchedType, params: dict) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.calendar = Gtk.Calendar()

        now = datetime.now()
        run_at_str = params.get("run_at") if current_type == SchedType.ONCE else None
        try:
            chosen = datetime.fromisoformat(run_at_str) if run_at_str else now
        except (TypeError, ValueError):
            chosen = now
        self.calendar.select_month(chosen.month - 1, chosen.year)
        self.calendar.select_day(chosen.day)

        time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        time_row.pack_start(Gtk.Label(label="Время:"), False, False, 0)
        self.once_hour = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.once_hour.set_value(chosen.hour)
        self.once_minute = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.once_minute.set_value(chosen.minute)
        time_row.pack_start(self.once_hour, False, False, 0)
        time_row.pack_start(Gtk.Label(label=":"), False, False, 0)
        time_row.pack_start(self.once_minute, False, False, 0)

        box.pack_start(self.calendar, True, True, 0)
        box.pack_start(time_row, False, False, 0)
        self.stack.add_titled(box, _STACK_NAMES[SchedType.ONCE], _STACK_TITLES["once"])

    def _build_interval_page(self, current_type: SchedType, params: dict) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.pack_start(Gtk.Label(label="Каждые"), False, False, 0)
        self.interval_every = Gtk.SpinButton.new_with_range(1, 9999, 1)
        every = int(params.get("every", 30) or 30) if current_type == SchedType.INTERVAL else 30
        self.interval_every.set_value(every)
        row.pack_start(self.interval_every, False, False, 0)

        self.interval_unit = Gtk.ComboBoxText()
        self.interval_unit.append("minutes", "минут")
        self.interval_unit.append("hours", "часов")
        unit_id = params.get("unit", "minutes") if current_type == SchedType.INTERVAL else "minutes"
        self.interval_unit.set_active_id(unit_id if unit_id in ("minutes", "hours") else "minutes")
        row.pack_start(self.interval_unit, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.stack.add_titled(box, _STACK_NAMES[SchedType.INTERVAL], _STACK_TITLES["interval"])

    def _build_weekly_page(self, current_type: SchedType, params: dict) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        days_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        active_days: set[str] = set()
        if current_type == SchedType.WEEKLY:
            active_days = set(params.get("days") or [])

        self.weekday_buttons: dict[str, Gtk.CheckButton] = {}
        for day in WEEKDAYS:
            cb = Gtk.CheckButton(label=_WEEKDAYS_LABELS[day])
            cb.set_active(day in active_days)
            self.weekday_buttons[day] = cb
            days_row.pack_start(cb, False, False, 0)
        box.pack_start(days_row, False, False, 0)

        times_label = Gtk.Label(label="Времена (через запятую, формат ЧЧ:ММ)", xalign=0.0)
        box.pack_start(times_label, False, False, 0)
        self.weekly_times_entry = Gtk.Entry()
        if current_type == SchedType.WEEKLY:
            times = params.get("times")
            if not times:
                single = params.get("time")
                times = [single] if single else []
            self.weekly_times_entry.set_text(", ".join(times) if times else "09:00")
        else:
            self.weekly_times_entry.set_text("09:00")
        box.pack_start(self.weekly_times_entry, False, False, 0)

        self.stack.add_titled(box, _STACK_NAMES[SchedType.WEEKLY], _STACK_TITLES["weekly"])

    def _build_cron_page(self, current_type: SchedType, params: dict) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.pack_start(
            Gtk.Label(label="Cron-выражение (5 полей: m h dom mon dow)", xalign=0.0),
            False,
            False,
            0,
        )
        self.cron_entry = Gtk.Entry()
        expr = params.get("expr") if current_type == SchedType.CRON else "0 9 * * *"
        self.cron_entry.set_text(expr or "0 9 * * *")
        box.pack_start(self.cron_entry, False, False, 0)
        self.cron_hint = Gtk.Label(label="Пример: 0 * * * * — каждый час в :00", xalign=0.0)
        box.pack_start(self.cron_hint, False, False, 0)
        self.stack.add_titled(box, _STACK_NAMES[SchedType.CRON], _STACK_TITLES["cron"])

    # ── collection ────────────────────────────────────────────────────────
    def _current_sched_type(self) -> SchedType:
        name = self.stack.get_visible_child_name() or "once"
        for st, key in _STACK_NAMES.items():
            if key == name:
                return st
        return SchedType.ONCE

    def _collect_params(self, sched_type: SchedType) -> dict | None:
        if sched_type == SchedType.ONCE:
            year, month_zero_based, day = self.calendar.get_date()
            try:
                dt = datetime(
                    year,
                    month_zero_based + 1,
                    day,
                    int(self.once_hour.get_value()),
                    int(self.once_minute.get_value()),
                )
            except ValueError as exc:
                self._warn(f"Неверная дата/время: {exc}")
                return None
            return {"run_at": dt.isoformat(timespec="seconds")}

        if sched_type == SchedType.INTERVAL:
            every = int(self.interval_every.get_value())
            unit = self.interval_unit.get_active_id() or "minutes"
            if every < 1:
                self._warn("Интервал должен быть положительным")
                return None
            return {"every": every, "unit": unit, "start_at": None}

        if sched_type == SchedType.WEEKLY:
            days = [d for d, btn in self.weekday_buttons.items() if btn.get_active()]
            if not days:
                self._warn("Выберите хотя бы один день недели")
                return None
            raw = self.weekly_times_entry.get_text().strip()
            times: list[str] = []
            for chunk in raw.replace(";", ",").split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    h_str, m_str = chunk.split(":")
                    h, m = int(h_str), int(m_str)
                    if not (0 <= h < 24 and 0 <= m < 60):
                        raise ValueError
                except ValueError:
                    self._warn(f"Неверное время: {chunk!r}")
                    return None
                times.append(f"{h:02d}:{m:02d}")
            if not times:
                self._warn("Укажите хотя бы одно время")
                return None
            return {"days": days, "times": times}

        if sched_type == SchedType.CRON:
            expr = self.cron_entry.get_text().strip()
            if not expr or len(expr.split()) != 5:
                self._warn("Cron должен содержать 5 полей: m h dom mon dow")
                return None
            return {"expr": expr}

        return None

    def _warn(self, text: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        )
        dialog.run()
        dialog.destroy()

    def run_and_collect(self) -> Reminder | None:
        while True:
            response = self.run()
            if response != Gtk.ResponseType.OK:
                return None

            sched_type = self._current_sched_type()
            params = self._collect_params(sched_type)
            if params is None:
                continue

            title = self.entry_title.get_text().strip() or "Напоминание"
            message = self.entry_message.get_text().strip()
            sound = self.chk_sound.get_active()
            enabled = self.chk_enabled.get_active()

            # Past-date warning for one-shot reminders (non-blocking confirmation).
            if sched_type == SchedType.ONCE:
                try:
                    when = datetime.fromisoformat(params["run_at"])
                    if when < datetime.now():
                        confirm = Gtk.MessageDialog(
                            transient_for=self,
                            flags=0,
                            message_type=Gtk.MessageType.WARNING,
                            buttons=Gtk.ButtonsType.OK_CANCEL,
                            text="Выбрано время в прошлом — напоминание не сработает.",
                        )
                        choice = confirm.run()
                        confirm.destroy()
                        if choice != Gtk.ResponseType.OK:
                            continue
                except ValueError:
                    pass

            if self._reminder is None:
                return Reminder(
                    title=title,
                    message=message,
                    enabled=enabled,
                    sound=sound,
                    sched_type=sched_type,
                    sched_params=params,
                )

            self._reminder.title = title
            self._reminder.message = message
            self._reminder.enabled = enabled
            self._reminder.sound = sound
            self._reminder.sched_type = sched_type
            self._reminder.sched_params = params
            return self._reminder
