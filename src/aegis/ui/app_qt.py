"""Qt application shell + page router.

QStackedWidget + Sidebar. Pages are registered in :data:`PAGES`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from aegis.core.config import Config
from aegis.ui.theme import apply, qpalette, qss
from aegis.ui.widgets.qt import Sidebar, ToastHost, NavItem


@dataclass(slots=True, frozen=True)
class PageSpec:
    key: str
    label: str
    icon: str
    factory: callable  # type: ignore[type-arg]


_NAV_ITEMS = [
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


class MainWindow(QMainWindow):
    """Top-level Qt window."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        apply(self.config.theme, self.config.accent)
        self.setWindowTitle("Aegis Linux")
        self.resize(1280, 780)
        self.setMinimumSize(960, 600)
        self.setStyleSheet(qss())
        self.setPalette(qpalette())

        # Central layout: [sidebar | stacked]
        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.sidebar = Sidebar(_NAV_ITEMS, width=200)
        self.sidebar.selected.connect(self.show_page)
        h.addWidget(self.sidebar)

        # Right column: [header | stacked | status]
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        self._header = QLabel("Dashboard")
        self._header.setStyleSheet(
            "font-size: 16pt; font-weight: 600; padding: 14px 24px;"
            f" background: {self._palette_bg2()};"
            f" border-bottom: 1px solid {self._palette_border()};"
        )
        rv.addWidget(self._header)

        self.stack = QStackedWidget()
        rv.addWidget(self.stack, 1)

        self.status = QStatusBar()
        self.status.showMessage("Ready.")
        rv.addWidget(self.status)

        h.addWidget(right, 1)

        self.toasts = ToastHost(self)
        self._pages: dict[str, QWidget] = {}
        self._register_pages()

        # Page router
        self.sidebar.select("dashboard")
        self.show_page("dashboard")

        # Cmd+Q / Ctrl+Q to quit
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)

    def _palette_bg2(self) -> str:
        from aegis.ui.theme import current as _cur
        return _cur().bg2

    def _palette_border(self) -> str:
        from aegis.ui.theme import current as _cur
        return _cur().border

    def show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        # Cross-fade between pages — the new page fades in over the
        # old one for 180ms, both composited by the GPU.
        cur = self.stack.currentWidget()
        if cur is not None and cur is not page:
            eff = QGraphicsOpacityEffect(cur)
            cur.setGraphicsEffect(eff)
            anim_out = QPropertyAnimation(eff, b"opacity", self)
            anim_out.setDuration(120)
            anim_out.setStartValue(1.0)
            anim_out.setEndValue(0.0)
            anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
            anim_out.start()
            anim_out.finished.connect(lambda c=cur: c.setGraphicsEffect(None))
        self.stack.setCurrentWidget(page)
        self._header.setText(key.capitalize())
        eff_in = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(eff_in)
        anim_in = QPropertyAnimation(eff_in, b"opacity", self)
        anim_in.setDuration(180)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_in.start()
        anim_in.finished.connect(lambda p=page: p.setGraphicsEffect(None))
        # Allow pages to react
        if hasattr(page, "on_show"):
            try:
                page.on_show()  # type: ignore[attr-defined]
            except Exception:
                pass

    def _register_pages(self) -> None:
        # Imported here to avoid circular import.
        from aegis.ui.pages.qt_pages import build_pages
        factories = build_pages(self)
        for key, widget in factories.items():
            self._pages[key] = widget
            self.stack.addWidget(widget)

    def show_toast(self, text: str, kind: str = "info") -> None:
        self.toasts.show_toast(text, kind=kind)


def launch_gui(config: Config | None = None) -> int:
    """Entry point used by ``python -m aegis``."""
    app = QApplication.instance() or QApplication(sys.argv)
    # Force the Qt RHI to use the desktop OpenGL backend so all
    # QPainter, QPropertyAnimation and PyQt6-Charts drawing is
    # composited by the GPU instead of the XRender / software path.
    # Falls back to software if no GL is available.
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_UseDesktopOpenGL, True)
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app.setApplicationName("Aegis Linux")
    app.setOrganizationName("Aegis")
    win = MainWindow(config or Config.load())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(launch_gui())