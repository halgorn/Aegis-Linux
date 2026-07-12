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
from aegis.core.i18n import tr
from aegis.ui.theme import apply, qpalette, qss
from aegis.ui.widgets.qt import Sidebar, ToastHost, NavItem


@dataclass(slots=True, frozen=True)
class PageSpec:
    key: str
    label: str
    icon: str
    factory: callable  # type: ignore[type-arg]


# Labels are i18n keys; the Sidebar translates them on render so
# users see the active locale without a restart.
_NAV_ITEMS = [
    NavItem("dashboard", "nav.dashboard", "⌂"),
    NavItem("cleaner", "nav.cleaner", "⚙"),
    NavItem("monitor", "nav.monitor", "▣"),
    NavItem("performance", "nav.performance", "↗"),
    NavItem("health", "nav.health", "♥"),
    NavItem("security", "nav.security", "⌖"),
    NavItem("network", "nav.network", "⇆"),
    NavItem("disks", "nav.disks", "◉"),
    NavItem("drivers", "nav.drivers", "✦"),
    NavItem("packages", "nav.packages", "▤"),
    NavItem("startup", "nav.startup", "▶"),
    NavItem("restore", "nav.restore", "⤺"),
    NavItem("logs", "nav.logs", "☰"),
    NavItem("settings", "nav.settings", "✱"),
]

# "Simple mode" — only the essentials. The advanced pages are hidden
# from the sidebar but still reachable via direct route / settings.
_SIMPLE_NAV_KEYS = frozenset({"dashboard", "cleaner", "health"})


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

    def set_locale(self, code: str) -> None:
        """Change language at runtime and refresh all visible labels."""
        from aegis.core import i18n
        i18n.set_locale(code)
        self.sidebar.retranslate()
        for page in self._pages.values():
            if hasattr(page, "retranslate"):
                try:
                    page.retranslate()
                except Exception:  # noqa: BLE001
                    pass

    def show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        # Cancel any in-flight scan on the page being left so the UI
        # thread doesn't get spammed with stale callbacks when the
        # user is already looking at a different page.
        cur = self.stack.currentWidget()
        if cur is not None and cur is not page:
            if hasattr(cur, "cancel_pending"):
                try:
                    cur.cancel_pending()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
            # Cross-fade between pages — the new page fades in over the
            # old one for 180ms, both composited by the GPU.
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
        # Allow pages to react (start their lazy scans on first show)
        if hasattr(page, "on_show"):
            try:
                page.on_show()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
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
    # Qt docs are explicit: the OpenGL backend attribute MUST be set
    # before the QCoreApplication (and therefore the QApplication) is
    # constructed. Calling it after is silently ignored and logs a
    # warning at best. So we set it first.
    if QApplication.instance() is None:
        QApplication.setAttribute(
            Qt.ApplicationAttribute.AA_UseDesktopOpenGL, True)
        QApplication.setAttribute(
            Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Aegis Linux")
    app.setOrganizationName("Aegis")
    win = MainWindow(config or Config.load())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(launch_gui())