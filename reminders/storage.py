"""SQLite-backed storage for reminders and key/value settings."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from reminders import paths
from reminders.models import Reminder, SchedType, now_iso

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


_MIGRATIONS: list[str] = [
    # v1: initial schema.
    """
    CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        message TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        sound INTEGER NOT NULL DEFAULT 1,
        sched_type TEXT NOT NULL,
        sched_params TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """,
]


class Storage:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or paths.db_file()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # ── lifecycle ──────────────────────────────────────────────────────────
    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            log.warning("Failed to close SQLite connection", exc_info=True)

    def _migrate(self) -> None:
        cur = self.conn.execute("PRAGMA user_version")
        current = cur.fetchone()[0]
        if current >= SCHEMA_VERSION:
            return
        for idx in range(current, SCHEMA_VERSION):
            log.info("Applying migration %d → %d", idx, idx + 1)
            self.conn.executescript(_MIGRATIONS[idx])
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    # ── CRUD ───────────────────────────────────────────────────────────────
    def list_reminders(self) -> list[Reminder]:
        cur = self.conn.execute("SELECT * FROM reminders ORDER BY datetime(updated_at) DESC")
        return [Reminder.from_row(dict(r)) for r in cur.fetchall()]

    def get(self, reminder_id: str) -> Reminder | None:
        cur = self.conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        row = cur.fetchone()
        return Reminder.from_row(dict(row)) if row else None

    def upsert(self, reminder: Reminder) -> Reminder:
        reminder.updated_at = now_iso()
        row = reminder.to_row()
        self.conn.execute(
            """
            INSERT INTO reminders
              (id, title, message, enabled, sound, sched_type, sched_params,
               created_at, updated_at)
            VALUES
              (:id, :title, :message, :enabled, :sound, :sched_type,
               :sched_params, :created_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
              title = excluded.title,
              message = excluded.message,
              enabled = excluded.enabled,
              sound = excluded.sound,
              sched_type = excluded.sched_type,
              sched_params = excluded.sched_params,
              updated_at = excluded.updated_at
            """,
            row,
        )
        self.conn.commit()
        return reminder

    def set_enabled(self, reminder_id: str, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE reminders SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, now_iso(), reminder_id),
        )
        self.conn.commit()

    def delete(self, reminder_id: str) -> None:
        self.conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self.conn.commit()

    # ── settings (key/value) ───────────────────────────────────────────────
    def get_setting(self, key: str, default: Any = None) -> Any:
        cur = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return default

    def set_setting(self, key: str, value: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO settings(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def all_settings(self) -> dict[str, Any]:
        cur = self.conn.execute("SELECT key, value FROM settings")
        out: dict[str, Any] = {}
        for row in cur.fetchall():
            try:
                out[row["key"]] = json.loads(row["value"])
            except (TypeError, json.JSONDecodeError):
                out[row["key"]] = row["value"]
        return out

    # ── helpers ────────────────────────────────────────────────────────────
    def enabled_reminders(self) -> Iterable[Reminder]:
        return (r for r in self.list_reminders() if r.enabled)

    def mark_once_fired(self, reminder_id: str) -> None:
        """Once-reminders disable themselves after they fire."""
        reminder = self.get(reminder_id)
        if reminder is None or reminder.sched_type != SchedType.ONCE:
            return
        self.set_enabled(reminder_id, False)
