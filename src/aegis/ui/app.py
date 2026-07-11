"""Main Aegis application — root window with sidebar navigation.

Wires together the theme, the main-thread bridge, the sidebar, and
each page. Pages are created lazily on first navigation so the
startup is fast.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from aegis.core.config import Config
from aegis.core.concurrency import MainThreadInvoker
from aegis.ui.theme import DARK, LIGHT, apply, current, font
from aegis.ui.widgets.common import apply_tree_style
from aegis.ui.widgets.sidebar import NavItem, Sidebar
from aegis.ui.widgets.toast import ToastHost


_NAV = [
    NavItem("dashboard", "Dashboard", "⌂"),
    NavItem("cleaner", "Cleaner", "⚙"),
    NavItem("monitor", "Monitor", "▣"),
    NavItem("performance", "Performance", "↗"),
    NavItem("health", "Health", "♥"),
    NavItem("security", "Security", "⌖"),
    NavItem("network", "Network", "⇆"),
    NavItem("disks", "Disks", "◉"),
    NavItem("drivers", "Drivers", "✦"),
    NavItem("packages", "Packages", "▤"),
    NavItem("startup", "Startup", "▶"),
    NavItem("restore", "Restore", "⤺"),
    NavItem("logs", "Logs", "☰"),
    NavItem("settings", "Settings", "✱"),
]


class AegisApp:
    """Top-level coordinator. Wraps a :class:`tk.Tk`."""

    def __init__(self, root: tk.Tk, config: Config | None = None) -> None:
        self.root = root
        self.config = config or Config.load()
        apply(self.config.theme, self.config.accent)
        apply_tree_style()

        # Main-thread bridge for worker → UI callbacks.
        self.bridge = MainThreadInvoker(root)
        # Expose the bridge on the root for pages to find.
        root._aegis_bridge = self.bridge

        self.toasts = ToastHost(root)

        self._pages: dict[str, tk.Widget] = {}
        self._current: str | None = None

        self._build_chrome()
        self._build_sidebar()
        self._show("dashboard")

    # ── chrome ────────────────────────────────────────────────────────

    def _build_chrome(self) -> None:
        self.root.title("Aegis Linux")
        self.root.geometry("1280x780")
        self.root.minsize(960, 600)
        self.root.configure(bg=current().bg)

        # Header bar
        self._header = tk.Frame(self.root, bg=current().bg2, pady=8)
        self._header.pack(fill="x", side="top")
        self._title_lbl = tk.Label(self._header, text="Dashboard",
                                    font=("Helvetica", 14, "bold"),
                                    fg=current().blue, bg=current().bg2)
        self._title_lbl.pack(side="left", padx=20)

        # Body container (sidebar + content)
        self._body = tk.Frame(self.root, bg=current().bg)
        self._body.pack(fill="both", expand=True)

        # Content frame (right of sidebar)
        self._content = tk.Frame(self._body, bg=current().bg)
        self._content.pack(side="left", fill="both", expand=True)

        # Status bar
        self._status = tk.StringVar(value="Ready.")
        self._status_bar = tk.Label(self.root, textvariable=self._status,
                                     fg=current().fg2, bg=current().bg2,
                                     font=font(9), anchor="w",
                                     padx=14, pady=4)
        self._status_bar.pack(fill="x", side="bottom")

    def _build_sidebar(self) -> None:
        self._sidebar = Sidebar(
            self._body, _NAV,
            on_select=self._show,
            width=200,
        )
        self._sidebar.pack(side="left", fill="y")

    # ── routing ───────────────────────────────────────────────────────

    def _show(self, key: str) -> None:
        if self._current == key:
            return
        # Hide current
        if self._current and self._current in self._pages:
            cur = self._pages[self._current]
            try:
                if hasattr(cur, "on_hide"):
                    cur.on_hide()
            except Exception:  # noqa: BLE001
                pass
            cur.pack_forget()

        # Build / show new
        page = self._pages.get(key)
        if page is None:
            page = self._build_page(key)
            self._pages[key] = page
        page.pack(fill="both", expand=True)
        try:
            if hasattr(page, "on_show"):
                page.on_show()
            if hasattr(page, "refresh"):
                page.refresh()
        except Exception:  # noqa: BLE001
            pass
        self._current = key
        self._title_lbl.config(text=key.capitalize())

    def _build_page(self, key: str) -> tk.Widget:
        if key == "dashboard":
            from aegis.ui.pages.dashboard import DashboardPage
            return DashboardPage(self._content, on_navigate=self._show)
        if key == "cleaner":
            from aegis.ui.pages.cleaner import CleanerPage
            return CleanerPage(self._content, toasts=self.toasts,
                                on_log=lambda s: self._set_status(s))
        if key == "monitor":
            from aegis.ui.pages.monitor import MonitorPage
            return MonitorPage(self._content, toasts=self.toasts)
        if key == "performance":
            from aegis.ui.pages.performance import PerformancePage
            return PerformancePage(self._content)
        if key == "health":
            from aegis.ui.pages.health import HealthPage
            return HealthPage(self._content, toasts=self.toasts)
        if key == "security":
            from aegis.ui.pages.security import SecurityPage
            return SecurityPage(self._content, toasts=self.toasts)
        if key == "network":
            from aegis.ui.pages.network import NetworkPage
            return NetworkPage(self._content, toasts=self.toasts)
        if key == "disks":
            from aegis.ui.pages.disks import DisksPage
            return DisksPage(self._content)
        if key == "drivers":
            from aegis.ui.pages.drivers import DriversPage
            return DriversPage(self._content)
        if key == "packages":
            from aegis.ui.pages.packages import PackagesPage
            return PackagesPage(self._content, toasts=self.toasts)
        if key == "startup":
            from aegis.ui.pages.startup import StartupPage
            return StartupPage(self._content, toasts=self.toasts)
        if key == "restore":
            from aegis.ui.pages.restore_points import RestorePointsPage
            return RestorePointsPage(self._content, toasts=self.toasts)
        if key == "logs":
            from aegis.ui.pages.logs import LogsPage
            return LogsPage(self._content)
        if key == "settings":
            from aegis.ui.pages.settings import SettingsPage
            return SettingsPage(self._content, on_apply=self._apply_settings)
        # Fallback: blank page
        return tk.Frame(self._content, bg=current().bg)

    def _apply_settings(self) -> None:
        apply(self.config.theme, self.config.accent)
        self.config.save()
        self.toasts.show("Settings saved.", kind="success")

    def _set_status(self, text: str) -> None:
        self._status.set(text)

    def run(self) -> None:
        self.root.mainloop()


def launch_gui() -> int:
    root = tk.Tk()
    AegisApp(root)
    AegisApp.run = AegisApp.run  # silence linter
    root.mainloop()
    return 0