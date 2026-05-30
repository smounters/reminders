"""libnotify wrapper. Optional ``snooze_cb`` adds an action button."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reminders import APP_NAME

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, app_name: str = APP_NAME, icon_name: str = "alarm-symbolic") -> None:
        self.app_name = app_name
        self.icon_name = icon_name
        self._ready = False
        self._notify = None
        self._init()

    def _init(self) -> None:
        try:
            import gi

            gi.require_version("Notify", "0.7")
            from gi.repository import Notify

            if not Notify.is_initted():
                Notify.init(self.app_name)
            self._notify = Notify
            self._ready = True
        except Exception:
            log.exception("Notify initialization failed; notifications disabled")
            self._ready = False

    @property
    def supports_actions(self) -> bool:
        if not self._ready:
            return False
        try:
            caps = list(self._notify.get_server_caps() or [])
            return "actions" in caps
        except Exception:
            return False

    def show(
        self,
        title: str,
        body: str,
        *,
        sound: bool = True,
        snooze_cb: Callable[[], None] | None = None,
    ) -> None:
        if not self._ready:
            log.info("notify: %s — %s", title, body)
            return

        try:
            Notify = self._notify
            notification = Notify.Notification.new(title or APP_NAME, body or "", self.icon_name)
            notification.set_urgency(Notify.Urgency.NORMAL)
            if sound:
                notification.set_hint_string("sound-name", "message")
            if snooze_cb is not None and self.supports_actions:

                def _on_snooze(_n, _action):
                    try:
                        snooze_cb()
                    except Exception:
                        log.exception("snooze callback failed")

                notification.add_action("snooze", "Отложить 10 мин", _on_snooze, None)
            notification.show()
        except Exception:
            log.exception("Failed to display notification")

    def shutdown(self) -> None:
        if not self._ready:
            return
        try:
            self._notify.uninit()
        except Exception:
            log.debug("Notify.uninit failed", exc_info=True)
