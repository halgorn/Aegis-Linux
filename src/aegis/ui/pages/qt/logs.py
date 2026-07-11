"""Logs page — recent system log entries."""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from aegis.services.logs_service import tail as tail_logs
from aegis.ui.widgets.qt import make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _run_scan, _wire_bridge,
)


class LogsPage(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        self._pending: list = []
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(make_title("Logs", "Recent system log entries."))
        self._view = QTextEdit(); self._view.setReadOnly(True)
        f = QFont("Monospace"); f.setStyleHint(QFont.StyleHint.Monospace)
        self._view.setFont(f)
        outer.addWidget(self._view, 1)

    def on_show(self) -> None:
        self._refresh()

    def _track(self, spec):
        self._pending.append(spec)

    def _untrack(self, spec):
        try:
            self._pending.remove(spec)
        except ValueError:
            pass

    def cancel_pending(self) -> None:
        for spec in list(self._pending):
            spec.cancel()
        self._pending.clear()

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge,
                  name="logs-fetch",
                  fn=lambda: tail_logs(lines=400),
                  on_render=self._render)

    def _render(self, r) -> None:
        self._view.setPlainText("\n".join(r.lines))