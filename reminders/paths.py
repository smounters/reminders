"""XDG-compliant paths for config, data and state directories."""

from __future__ import annotations

import os
from pathlib import Path

from reminders import APP_ID


def _xdg_dir(env_var: str, fallback: str) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value)
    return Path.home() / fallback


def config_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_ID


def data_dir() -> Path:
    return _xdg_dir("XDG_DATA_HOME", ".local/share") / APP_ID


def state_dir() -> Path:
    return _xdg_dir("XDG_STATE_HOME", ".local/state") / APP_ID


def autostart_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / "autostart"


def config_file() -> Path:
    return config_dir() / "config.json"


def db_file() -> Path:
    return data_dir() / "reminders.db"


def log_file() -> Path:
    return state_dir() / "app.log"


def autostart_file() -> Path:
    return autostart_dir() / f"{APP_ID}.desktop"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), state_dir()):
        d.mkdir(parents=True, exist_ok=True)
