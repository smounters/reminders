"""Manage ~/.config/autostart/<APP_ID>.desktop."""

from __future__ import annotations

import logging
import shutil

from reminders import APP_ID, APP_NAME, paths

log = logging.getLogger(__name__)


_DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name={name}
Comment=Tray reminder application
Exec={exec_cmd}
Icon={icon}
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""


def _exec_command() -> str:
    """Return the install-time entry point if available, else the dev path."""
    installed = shutil.which("reminders-gtk")
    if installed:
        return installed
    return "python3 -m reminders"


def is_enabled() -> bool:
    return paths.autostart_file().is_file()


def enable() -> None:
    target = paths.autostart_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = _DESKTOP_TEMPLATE.format(
        name=APP_NAME,
        exec_cmd=_exec_command(),
        icon=APP_ID,
    )
    target.write_text(content, encoding="utf-8")
    log.info("Autostart enabled at %s", target)


def disable() -> None:
    target = paths.autostart_file()
    if target.exists():
        target.unlink()
        log.info("Autostart disabled (removed %s)", target)


def set_enabled(enabled: bool) -> None:
    if enabled:
        enable()
    else:
        disable()
