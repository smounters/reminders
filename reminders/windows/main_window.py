"""Main window: list of reminders with toolbar (Add/Edit/Delete/Duplicate)."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from reminders import APP_NAME
from reminders.models import Reminder, describe_schedule

log = logging.getLogger(__name__)


# Columns: enabled, title, schedule, next_run, id (hidden)
COL_ENABLED = 0
COL_TITLE = 1
COL_SCHEDULE = 2
COL_NEXT_RUN = 3
COL_ID = 4


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: object) -> None:
        super().__init__(title=APP_NAME)
        self.app = app
        self.set_default_size(720, 480)
        self.set_border_width(0)
        self.connect("delete-event", self._on_delete_event)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.BOTH_HORIZ)
        vbox.pack_start(toolbar, False, False, 0)

        self.btn_add = Gtk.ToolButton.new(None, "Добавить")
        self.btn_add.set_icon_name("list-add-symbolic")
        self.btn_add.connect("clicked", self._on_add)
        toolbar.insert(self.btn_add, -1)

        self.btn_edit = Gtk.ToolButton.new(None, "Изменить")
        self.btn_edit.set_icon_name("document-edit-symbolic")
        self.btn_edit.connect("clicked", self._on_edit)
        toolbar.insert(self.btn_edit, -1)

        self.btn_duplicate = Gtk.ToolButton.new(None, "Дублировать")
        self.btn_duplicate.set_icon_name("edit-copy-symbolic")
        self.btn_duplicate.connect("clicked", self._on_duplicate)
        toolbar.insert(self.btn_duplicate, -1)

        self.btn_delete = Gtk.ToolButton.new(None, "Удалить")
        self.btn_delete.set_icon_name("edit-delete-symbolic")
        self.btn_delete.connect("clicked", self._on_delete)
        toolbar.insert(self.btn_delete, -1)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(scrolled, True, True, 0)

        # bool, str, str, str, str
        self.store = Gtk.ListStore(bool, str, str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.tree.connect("row-activated", self._on_row_activated)
        scrolled.add(self.tree)

        toggle_renderer = Gtk.CellRendererToggle()
        toggle_renderer.connect("toggled", self._on_enabled_toggled)
        self.tree.append_column(Gtk.TreeViewColumn("Вкл", toggle_renderer, active=COL_ENABLED))

        for title, idx, expand in (
            ("Заголовок", COL_TITLE, True),
            ("Расписание", COL_SCHEDULE, False),
            ("Следующее", COL_NEXT_RUN, False),
        ):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            col.set_resizable(True)
            col.set_expand(expand)
            self.tree.append_column(col)

    # ── helpers ───────────────────────────────────────────────────────────
    def _selected_id(self) -> str | None:
        selection = self.tree.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter is None:
            return None
        return model[treeiter][COL_ID]

    def refresh(self) -> None:
        try:
            self.store.clear()
            for reminder in self.app.storage.list_reminders():
                nxt = self.app.scheduler.next_run(reminder.id)
                self.store.append(
                    [
                        reminder.enabled,
                        reminder.title or "(без названия)",
                        describe_schedule(reminder.sched_type, reminder.sched_params),
                        nxt.strftime("%d.%m %H:%M") if nxt else "—",
                        reminder.id,
                    ]
                )
        except Exception:
            log.exception("MainWindow.refresh failed")

    # ── handlers ──────────────────────────────────────────────────────────
    def _on_delete_event(self, *_args) -> bool:
        # Hide instead of destroy → keep app alive in the tray.
        self.hide()
        return True

    def _on_enabled_toggled(self, _renderer, path) -> None:
        treeiter = self.store.get_iter(path)
        new_value = not self.store[treeiter][COL_ENABLED]
        reminder_id = self.store[treeiter][COL_ID]
        self.store[treeiter][COL_ENABLED] = new_value
        self.app.set_reminder_enabled(reminder_id, new_value)
        self.refresh()

    def _on_add(self, *_args) -> None:
        from reminders.windows.edit_dialog import EditDialog

        dialog = EditDialog(parent=self, reminder=None)
        new_reminder = dialog.run_and_collect()
        dialog.destroy()
        if new_reminder is not None:
            self.app.save_reminder(new_reminder)

    def _open_edit_for(self, reminder_id: str) -> None:
        from reminders.windows.edit_dialog import EditDialog

        reminder = self.app.storage.get(reminder_id)
        if reminder is None:
            return
        dialog = EditDialog(parent=self, reminder=reminder)
        updated = dialog.run_and_collect()
        dialog.destroy()
        if updated is not None:
            self.app.save_reminder(updated)

    def _on_edit(self, *_args) -> None:
        reminder_id = self._selected_id()
        if reminder_id is not None:
            self._open_edit_for(reminder_id)

    def _on_row_activated(self, _tree, path, _column) -> None:
        treeiter = self.store.get_iter(path)
        reminder_id = self.store[treeiter][COL_ID]
        self._open_edit_for(reminder_id)

    def _on_duplicate(self, *_args) -> None:
        reminder_id = self._selected_id()
        if reminder_id is None:
            return
        original = self.app.storage.get(reminder_id)
        if original is None:
            return
        copy = Reminder(
            title=f"{original.title} (копия)",
            message=original.message,
            enabled=original.enabled,
            sound=original.sound,
            sched_type=original.sched_type,
            sched_params=dict(original.sched_params),
        )
        self.app.save_reminder(copy)

    def _on_delete(self, *_args) -> None:
        reminder_id = self._selected_id()
        if reminder_id is None:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Удалить напоминание?",
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self.app.delete_reminder(reminder_id)
