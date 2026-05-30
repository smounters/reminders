"""Application entry point.

Boots logging, builds storage/scheduler/tray/notifier and runs the GTK
main loop. Supports a non-interactive ``--selftest`` mode for CI.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

from reminders import APP_ID, APP_NAME, paths
from reminders.autostart import is_enabled as autostart_is_enabled
from reminders.models import Reminder, SchedType
from reminders.notifier import Notifier
from reminders.scheduler import ReminderScheduler
from reminders.storage import Storage

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    paths.ensure_dirs()
    level_name = os.environ.get("REMINDERS_LOG", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(str(paths.log_file()), encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


# ── self-test ───────────────────────────────────────────────────────────────
def _run_selftest() -> int:
    """Boot enough of the app to verify GTK/Notify/AppIndicator/APScheduler
    on a headless CI runner. Never enters Gtk.main()."""
    import tempfile
    from pathlib import Path

    _setup_logging()
    log.info("Selftest: starting")

    # GTK + AppIndicator import probe.
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Notify", "0.7")
        from gi.repository import Gtk  # noqa: F401

        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as _ind  # noqa: F401

            log.info("Selftest: AyatanaAppIndicator3 OK")
        except (ValueError, ImportError):
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3 as _ind  # noqa: F401

            log.info("Selftest: AppIndicator3 (legacy) OK")

        from gi.repository import Notify

        Notify.init(APP_NAME)
        Notify.uninit()
    except Exception as exc:
        log.exception("Selftest: GUI/Notify probe failed")
        print(f"selftest FAIL: GUI probe: {exc}", file=sys.stderr)
        return 1

    # Storage + scheduler probe with a throwaway DB.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "selftest.db"
            storage = Storage(db_path=db)
            run_at = (datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds")
            reminder = Reminder(
                title="selftest",
                message="ok",
                sched_type=SchedType.ONCE,
                sched_params={"run_at": run_at},
            )
            storage.upsert(reminder)

            fired: list[str] = []

            def fire(reminder_id: str) -> None:
                fired.append(reminder_id)

            sched = ReminderScheduler(fire)
            sched.start()
            try:
                sched.register(reminder)
                nxt = sched.next_run(reminder.id)
                if nxt is None:
                    raise RuntimeError("next_run is None")
                log.info("Selftest: next_run=%s", nxt.isoformat())
            finally:
                sched.shutdown()
                storage.close()
    except Exception as exc:
        log.exception("Selftest: scheduler/storage probe failed")
        print(f"selftest FAIL: scheduler/storage: {exc}", file=sys.stderr)
        return 1

    print("selftest OK")
    return 0


# ── full application ────────────────────────────────────────────────────────
class RemindersApp:
    """Holds the singletons (storage, scheduler, notifier, GUI) together."""

    def __init__(self) -> None:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gio, GLib, Gtk

        self.Gio = Gio
        self.GLib = GLib
        self.Gtk = Gtk

        self.storage = Storage()
        self.notifier = Notifier()
        self.scheduler = ReminderScheduler(self._fire_from_thread)

        self.gtk_app: Gtk.Application | None = None
        self.tray = None  # type: ignore[assignment]
        self.main_window = None  # type: ignore[assignment]

    # ── lifecycle ─────────────────────────────────────────────────────────
    def build(self) -> None:
        from reminders.tray import Tray
        from reminders.windows.main_window import MainWindow

        self.gtk_app = self.Gtk.Application(
            application_id=APP_ID,
            flags=self.Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.gtk_app.connect("activate", self._on_activate)
        self.gtk_app.connect("shutdown", self._on_shutdown)

        self.main_window = MainWindow(self)
        self.tray = Tray(self)

        self.scheduler.reload(self.storage.list_reminders())
        self.scheduler.start()
        self.tray.refresh_status()

    def run(self, argv: list[str]) -> int:
        self.build()
        assert self.gtk_app is not None
        return self.gtk_app.run(argv)

    def quit(self) -> None:
        if self.gtk_app is not None:
            self.gtk_app.quit()

    # ── GTK callbacks ─────────────────────────────────────────────────────
    def _on_activate(self, app) -> None:
        # Second launch activates the existing instance → show window.
        self.show_main_window()

    def _on_shutdown(self, _app) -> None:
        self.scheduler.shutdown()
        self.notifier.shutdown()
        self.storage.close()

    # ── public API used by tray/windows ───────────────────────────────────
    def show_main_window(self) -> None:
        if self.main_window is None:
            return
        if self.gtk_app is not None and self.main_window.get_application() is None:
            self.main_window.set_application(self.gtk_app)
        self.main_window.present()
        self.main_window.refresh()

    def toggle_pause(self) -> None:
        if self.scheduler.paused:
            self.scheduler.resume()
        else:
            self.scheduler.pause()
        if self.tray is not None:
            self.tray.refresh_status()

    def save_reminder(self, reminder: Reminder) -> None:
        self.storage.upsert(reminder)
        self.scheduler.register(reminder)
        if self.main_window is not None:
            self.main_window.refresh()
        if self.tray is not None:
            self.tray.refresh_status()

    def delete_reminder(self, reminder_id: str) -> None:
        self.scheduler.unregister(reminder_id)
        self.storage.delete(reminder_id)
        if self.main_window is not None:
            self.main_window.refresh()
        if self.tray is not None:
            self.tray.refresh_status()

    def set_reminder_enabled(self, reminder_id: str, enabled: bool) -> None:
        self.storage.set_enabled(reminder_id, enabled)
        reminder = self.storage.get(reminder_id)
        if reminder is None:
            return
        self.scheduler.register(reminder)
        if self.tray is not None:
            self.tray.refresh_status()

    def autostart_enabled(self) -> bool:
        return autostart_is_enabled()

    # ── fire path (runs on APScheduler worker thread) ─────────────────────
    def _fire_from_thread(self, reminder_id: str) -> None:
        # Must marshal GTK/Notify calls back to the main loop.
        self.GLib.idle_add(self._fire_on_main, reminder_id)

    def _fire_on_main(self, reminder_id: str) -> bool:
        try:
            reminder = self.storage.get(reminder_id)
            if reminder is None or not reminder.enabled:
                return False

            def _snooze() -> None:
                # Add a +10m one-shot job that fires the same reminder once.
                from datetime import datetime, timedelta

                from apscheduler.triggers.date import DateTrigger

                run_at = datetime.now() + timedelta(minutes=10)
                job_id = f"{reminder_id}#snooze#{int(run_at.timestamp())}"
                try:
                    self.scheduler.scheduler.add_job(
                        self.scheduler._dispatch,
                        trigger=DateTrigger(run_date=run_at),
                        id=job_id,
                        args=[reminder_id],
                        replace_existing=True,
                        misfire_grace_time=60,
                    )
                except Exception:
                    log.exception("Failed to schedule snooze for %s", reminder_id)

            self.notifier.show(
                reminder.title,
                reminder.message,
                sound=reminder.sound,
                snooze_cb=_snooze,
            )

            if reminder.sched_type == SchedType.ONCE:
                self.storage.mark_once_fired(reminder_id)
                self.scheduler.unregister(reminder_id)
                if self.main_window is not None:
                    self.main_window.refresh()
                if self.tray is not None:
                    self.tray.refresh_status()
        except Exception:
            log.exception("Failed to fire reminder %s", reminder_id)
        return False  # one-shot idle handler


# ── main ────────────────────────────────────────────────────────────────────
def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="reminders-gtk", description=APP_NAME)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Non-interactive self-check used by CI; does not enter the GTK loop.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args(sys.argv[1:])
    if args.selftest:
        return _run_selftest()

    _setup_logging()
    log.info("Starting %s (%s)", APP_NAME, APP_ID)
    try:
        app = RemindersApp()
    except Exception:
        log.exception("Failed to bootstrap application")
        return 1
    # Don't forward --selftest etc. to Gtk.Application; only pass argv[0].
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    raise SystemExit(main())
