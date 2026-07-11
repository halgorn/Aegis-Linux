"""Security page — permissions, listeners, firewall, SSH, AV."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.services.security_service import SecurityService
from aegis.ui.widgets.qt import make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _run_scan, _wire_bridge,
)


class SecurityPage(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        self._pending: list = []
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._svc = SecurityService()
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(make_title("Security", "Permissions, listeners, firewall, SSH, AV."))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Name", "Severity", "Detail", "Suggestion"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        outer.addWidget(self._tbl, 1)

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
                  name="sec-scan", fn=self._svc.scan, on_render=self._render)

    def _render(self, findings) -> None:
        self._tbl.setRowCount(len(findings))
        for i, c in enumerate(findings):
            self._tbl.setItem(i, 0, QTableWidgetItem(c.code))
            sev = c.severity
            sev_label = sev.label if hasattr(sev, "label") else str(sev)
            self._tbl.setItem(i, 1, QTableWidgetItem(sev_label.upper()))
            self._tbl.setItem(i, 2, QTableWidgetItem(c.title))
            self._tbl.setItem(i, 3, QTableWidgetItem((c.detail or "")[:120]))