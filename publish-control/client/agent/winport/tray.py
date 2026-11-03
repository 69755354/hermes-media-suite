"""Tray shell (Mac LSUIElement menu-bar analogue).

pystray is optional: on the Linux static test it is absent and the tray
degrades to a headless no-op so the daemon loop can still be exercised.
"""

from __future__ import annotations

import threading


class TrayApp:
    def __init__(self, layout, on_check_now=None, on_open_reports=None,
                 on_open_panel=None, status_provider=None, logger=None):
        self.layout = layout
        self.on_check_now = on_check_now
        self.on_open_reports = on_open_reports
        self.on_open_panel = on_open_panel
        self.status_provider = status_provider
        self.logger = logger
        self._icon = None
        self._thread = None
        self.notifications = []

    @property
    def available(self) -> bool:
        try:
            import pystray  # noqa: F401
            from PIL import Image  # noqa: F401
            return True
        except ImportError:
            return False

    def notify(self, title, message, *, balloontip=True):
        """Native notification on Windows; recorded otherwise."""
        self.notifications.append({"title": title, "message": message})
        if self.logger:
            self.logger.info("notify: %s - %s", title, message)
        try:
            from win10toast import ToastNotifier  # type: ignore
            ToastNotifier().show_toast(title, message, duration=8,
                                       threaded=True)
            return True
        except Exception:
            return False

    def start(self) -> bool:
        if not self.available:
            if self.logger:
                self.logger.info("pystray/Pillow absent: tray disabled (headless)")
            return False
        import pystray
        from PIL import Image
        image = Image.new("RGB", (64, 64), (32, 32, 32))

        def _check(icon, item):
            if self.on_check_now:
                self.on_check_now()

        def _reports(icon, item):
            if self.on_open_reports:
                self.on_open_reports()

        def _panel(icon, item):
            if self.on_open_panel:
                self.on_open_panel()

        items = [pystray.MenuItem("打开控制面板", _panel),
                 pystray.MenuItem("立即检查", _check),
                 pystray.MenuItem("打开报表", _reports)]
        rows = []
        if callable(self.status_provider):
            try:
                rows = self.status_provider() or []
            except Exception:
                rows = []
        if rows:
            items.append(pystray.Menu.SEPARATOR)
            for row in rows:
                label = (f"{row.get('platform_name', row.get('platform', '?'))}"
                         f" {row.get('nickname', '')}：{row.get('status', '?')}")
                items.append(pystray.MenuItem(label, None, enabled=False))
        menu = pystray.Menu(*items)
        self._icon = pystray.Icon("publish-assistant", image,
                                  "漫剧发布助手", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
