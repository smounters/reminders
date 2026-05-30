"""AppIndicator tray with Ayatana → legacy AppIndicator3 fallback."""

from __future__ import annotations

import logging
from typing import Any

from reminders import APP_ID, APP_NAME

log = logging.getLogger(__name__)


def _import_appindicator() -> tuple[Any, str]:
    """Return (AppIndicator module, gir name). Tries Ayatana first."""
    import gi

    for gir_name, attr in (
        ("AyatanaAppIndicator3", "AyatanaAppIndicator3"),
        ("AppIndicator3", "AppIndicator3"),
    ):
        try:
            gi.require_version(gir_name, "0.1")
            module = __import__("gi.repository", fromlist=[attr])
            return getattr(module, attr), gir_name
        except (ValueError, ImportError) as exc:
            log.debug("AppIndicator import %s failed: %s", gir_name, exc)
    raise RuntimeError("Neither AyatanaAppIndicator3 nor AppIndicator3 is available")


class Tray:
    def __init__(self, app: object) -> None:
        from gi.repository import Gtk

        self.app = app
        self.Gtk = Gtk

        AppIndicator, gir_name = _import_appindicator()
        log.info("Tray using %s", gir_name)

        self.indicator = AppIndicator.Indicator.new(
            APP_ID,
            "alarm-symbolic",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_NAME)

        self.status_item = Gtk.MenuItem(label="Следующее: —")
        self.status_item.set_sensitive(False)
        self.pause_item = Gtk.MenuItem(label="Пауза")

        menu = Gtk.Menu()
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())

        open_item = Gtk.MenuItem(label="Открыть окно")
        open_item.connect("activate", lambda *_: self.app.show_main_window())
        menu.append(open_item)

        self.pause_item.connect("activate", lambda *_: self.app.toggle_pause())
        menu.append(self.pause_item)

        add_item = Gtk.MenuItem(label="Добавить напоминание…")
        add_item.connect("activate", self._on_add)
        menu.append(add_item)

        settings_item = Gtk.MenuItem(label="Настройки…")
        settings_item.connect("activate", self._on_settings)
        menu.append(settings_item)

        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Выход")
        quit_item.connect("activate", lambda *_: self.app.quit())
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)
        self._menu = menu

    def refresh_status(self) -> None:
        try:
            if self.app.scheduler.paused:
                self.status_item.set_label("На паузе")
                self.pause_item.set_label("Возобновить")
                return

            self.pause_item.set_label("Пауза")
            nxt = self.app.scheduler.next_run_global()
            if nxt is None:
                self.status_item.set_label("Следующее: —")
            else:
                self.status_item.set_label("Следующее: " + nxt.strftime("%d.%m %H:%M"))
        except Exception:
            log.exception("refresh_status failed")

    # ── menu handlers ─────────────────────────────────────────────────────
    def _on_add(self, *_args) -> None:
        from reminders.windows.edit_dialog import EditDialog

        dialog = EditDialog(parent=None, reminder=None)
        new_reminder = dialog.run_and_collect()
        dialog.destroy()
        if new_reminder is not None:
            self.app.save_reminder(new_reminder)

    def _on_settings(self, *_args) -> None:
        from reminders.windows.settings_dialog import SettingsDialog

        dialog = SettingsDialog(parent=None, app=self.app)
        dialog.run()
        dialog.destroy()
