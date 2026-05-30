"""SQLite storage: schema migrations, CRUD, settings."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from reminders.models import Reminder, SchedType
from reminders.storage import SCHEMA_VERSION, Storage


@pytest.fixture()
def storage(tmp_path: Path) -> Storage:
    db = tmp_path / "test.db"
    s = Storage(db_path=db)
    yield s
    s.close()


def test_migration_sets_user_version(storage: Storage):
    cur = storage.conn.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == SCHEMA_VERSION


def test_migration_creates_tables(storage: Storage):
    tables = {
        row[0] for row in storage.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "reminders" in tables
    assert "settings" in tables


def test_migration_is_idempotent(tmp_path: Path):
    db = tmp_path / "again.db"
    Storage(db_path=db).close()
    s = Storage(db_path=db)
    try:
        cur = s.conn.execute("PRAGMA user_version")
        assert cur.fetchone()[0] == SCHEMA_VERSION
    finally:
        s.close()


def test_upsert_then_get_roundtrip(storage: Storage):
    r = Reminder(
        title="hello",
        message="world",
        sched_type=SchedType.WEEKLY,
        sched_params={"days": ["mon"], "times": ["09:00"]},
    )
    storage.upsert(r)
    fetched = storage.get(r.id)
    assert fetched is not None
    assert fetched.title == "hello"
    assert fetched.sched_type == SchedType.WEEKLY
    assert fetched.sched_params == {"days": ["mon"], "times": ["09:00"]}


def test_upsert_updates_existing(storage: Storage):
    r = Reminder(
        title="v1", sched_type=SchedType.ONCE, sched_params={"run_at": "2026-06-01T09:00:00"}
    )
    storage.upsert(r)
    r.title = "v2"
    storage.upsert(r)
    fetched = storage.get(r.id)
    assert fetched is not None
    assert fetched.title == "v2"
    assert len(storage.list_reminders()) == 1


def test_set_enabled(storage: Storage):
    r = Reminder(
        title="t", sched_type=SchedType.ONCE, sched_params={"run_at": "2026-06-01T09:00:00"}
    )
    storage.upsert(r)
    storage.set_enabled(r.id, False)
    fetched = storage.get(r.id)
    assert fetched is not None
    assert fetched.enabled is False


def test_delete(storage: Storage):
    r = Reminder(
        title="t", sched_type=SchedType.ONCE, sched_params={"run_at": "2026-06-01T09:00:00"}
    )
    storage.upsert(r)
    storage.delete(r.id)
    assert storage.get(r.id) is None


def test_settings_roundtrip(storage: Storage):
    storage.set_setting("quiet_enabled", True)
    storage.set_setting("quiet_from", "22:00")
    storage.set_setting("timezone", None)
    assert storage.get_setting("quiet_enabled") is True
    assert storage.get_setting("quiet_from") == "22:00"
    assert storage.get_setting("timezone") is None
    assert storage.get_setting("missing", "fallback") == "fallback"


def test_mark_once_fired_only_affects_once(storage: Storage):
    once = Reminder(
        title="o", sched_type=SchedType.ONCE, sched_params={"run_at": "2026-06-01T09:00:00"}
    )
    interval = Reminder(
        title="i", sched_type=SchedType.INTERVAL, sched_params={"every": 5, "unit": "minutes"}
    )
    storage.upsert(once)
    storage.upsert(interval)
    storage.mark_once_fired(once.id)
    storage.mark_once_fired(interval.id)
    assert storage.get(once.id).enabled is False
    assert storage.get(interval.id).enabled is True


def test_unicode_title_survives_roundtrip(storage: Storage):
    r = Reminder(
        title="Принять лекарство 💊",
        message="не забыть",
        sched_type=SchedType.INTERVAL,
        sched_params={"every": 30, "unit": "minutes"},
    )
    storage.upsert(r)
    fetched = storage.get(r.id)
    assert fetched is not None
    assert fetched.title == "Принять лекарство 💊"


def test_migration_starting_from_blank_db(tmp_path: Path):
    db = tmp_path / "blank.db"
    sqlite3.connect(str(db)).close()  # empty file, user_version = 0
    s = Storage(db_path=db)
    try:
        cur = s.conn.execute("PRAGMA user_version")
        assert cur.fetchone()[0] == SCHEMA_VERSION
    finally:
        s.close()
