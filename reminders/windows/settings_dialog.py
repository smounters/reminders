"""Global settings dialog: autostart, sound, quiet hours, timezone."""

from __future__ import annotations

import logging
from datetime import datetime, time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from reminders import autostart

log = logging.getLogger(__name__)


def _parse_hhmm(value: str | None, default: time) -> time:
    if not value:
        return default
    try:
        h_str, _, m_str = value.partition(":")
        return time(int(h_str), int(m_str or 0))
    except ValueError:
        return default


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window | None, app: object) -> None:
        super().__init__(title="Настройки", transient_for=parent, flags=0)
        self.app = app
        self.add_buttons(
            "_Отмена",
            Gtk.ResponseType.CANCEL,
            "_Сохранить",
            Gtk.ResponseType.OK,
        )
        self.set_default_size(420, 360)

        content = self.get_content_area()
        content.set_border_width(12)
        content.set_spacing(8)

        # Autostart
        self.chk_autostart = Gtk.CheckButton(label="Запускать при входе в сессию")
        self.chk_autostart.set_active(autostart.is_enabled())
        content.pack_start(self.chk_autostart, False, False, 0)

        # Sound default
        self.chk_sound_default = Gtk.CheckButton(label="Звук уведомлений по умолчанию")
        self.chk_sound_default.set_active(bool(app.storage.get_setting("sound_default", True)))
        content.pack_start(self.chk_sound_default, False, False, 0)

        # Quiet hours
        quiet_enabled = bool(app.storage.get_setting("quiet_enabled", False))
        self.chk_quiet = Gtk.CheckButton(label="Тихие часы")
        self.chk_quiet.set_active(quiet_enabled)
        content.pack_start(self.chk_quiet, False, False, 0)

        quiet_from = _parse_hhmm(app.storage.get_setting("quiet_from"), time(22, 0))
        quiet_to = _parse_hhmm(app.storage.get_setting("quiet_to"), time(8, 0))

        quiet_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        quiet_row.pack_start(Gtk.Label(label="С:"), False, False, 0)
        self.quiet_from_hour = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.quiet_from_hour.set_value(quiet_from.hour)
        self.quiet_from_min = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.quiet_from_min.set_value(quiet_from.minute)
        quiet_row.pack_start(self.quiet_from_hour, False, False, 0)
        quiet_row.pack_start(Gtk.Label(label=":"), False, False, 0)
        quiet_row.pack_start(self.quiet_from_min, False, False, 0)

        quiet_row.pack_start(Gtk.Label(label="  по:"), False, False, 0)
        self.quiet_to_hour = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.quiet_to_hour.set_value(quiet_to.hour)
        self.quiet_to_min = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.quiet_to_min.set_value(quiet_to.minute)
        quiet_row.pack_start(self.quiet_to_hour, False, False, 0)
        quiet_row.pack_start(Gtk.Label(label=":"), False, False, 0)
        quiet_row.pack_start(self.quiet_to_min, False, False, 0)
        content.pack_start(quiet_row, False, False, 0)

        # Timezone
        content.pack_start(
            Gtk.Label(label="Таймзона (IANA, пусто = системная):", xalign=0.0),
            False,
            False,
            0,
        )
        self.entry_tz = Gtk.Entry()
        self.entry_tz.set_text(str(app.storage.get_setting("timezone") or ""))
        self.entry_tz.set_placeholder_text(datetime.now().astimezone().tzname() or "")
        content.pack_start(self.entry_tz, False, False, 0)

        self.show_all()
        self.connect("response", self._on_response)

    def _on_response(self, _dialog, response_id) -> None:
        if response_id != Gtk.ResponseType.OK:
            return
        try:
            autostart.set_enabled(self.chk_autostart.get_active())
            self.app.storage.set_setting("sound_default", self.chk_sound_default.get_active())
            self.app.storage.set_setting("quiet_enabled", self.chk_quiet.get_active())
            self.app.storage.set_setting(
                "quiet_from",
                f"{int(self.quiet_from_hour.get_value()):02d}:"
                f"{int(self.quiet_from_min.get_value()):02d}",
            )
            self.app.storage.set_setting(
                "quiet_to",
                f"{int(self.quiet_to_hour.get_value()):02d}:"
                f"{int(self.quiet_to_min.get_value()):02d}",
            )
            tz = self.entry_tz.get_text().strip()
            self.app.storage.set_setting("timezone", tz or None)
        except Exception:
            log.exception("Failed to save settings")
