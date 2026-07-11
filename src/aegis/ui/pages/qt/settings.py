"""Settings page — theme, accent and safety options."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from aegis.ui.widgets.qt import make_section, make_title
from aegis.ui.pages.qt._helpers import _show_toast


class SettingsPage(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        win = host.window()
        self._cfg = getattr(win, "config", None)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title("Settings", "Theme, accent and safety options."))
        outer.addWidget(make_section("Appearance"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Theme"))
        self._theme = QComboBox()
        self._theme.addItems(["dark", "light"])
        if self._cfg:
            self._theme.setCurrentText(self._cfg.theme)
        row.addWidget(self._theme)
        row.addSpacing(20)
        row.addWidget(QLabel("Accent"))
        self._accent = QComboBox()
        self._accent.addItems(["blue", "green", "mauve", "pink"])
        if self._cfg:
            self._accent.setCurrentText(self._cfg.accent)
        row.addWidget(self._accent)
        row.addStretch()
        rw = QWidget(); rw.setLayout(row); outer.addWidget(rw)

        outer.addWidget(make_section("Safety"))
        self._dry = QCheckBox("Always preview cleaner with dry-run")
        self._dry.setChecked(True)
        outer.addWidget(self._dry)
        self._backup = QCheckBox("Create backup before every clean")
        self._backup.setChecked(True)
        outer.addWidget(self._backup)

        bar = QHBoxLayout(); bar.addStretch()
        apply_btn = QPushButton("Apply"); apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._apply)
        bar.addWidget(apply_btn)
        bw = QWidget(); bw.setLayout(bar); outer.addWidget(bw)

    def cancel_pending(self) -> None:
        pass

    def _apply(self) -> None:
        if not self._cfg:
            return
        from aegis.ui.theme import apply as apply_theme, qss as theme_qss
        from aegis.ui.app_qt import MainWindow
        self._cfg.theme = self._theme.currentText()
        self._cfg.accent = self._accent.currentText()
        try:
            self._cfg.save()
        except Exception:
            pass
        apply_theme(self._cfg.theme, self._cfg.accent)
        win = self.window()
        if isinstance(win, MainWindow):
            win.setStyleSheet(theme_qss())
        _show_toast(self, "Settings applied.", "success")