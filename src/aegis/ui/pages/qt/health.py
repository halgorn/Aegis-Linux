"""Health page — system wellness score + issues table."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.services.health_service import HealthService
from aegis.core.i18n import tr
from aegis.ui.widgets.qt import Gauge, ScanButton, make_section, make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _set_status, _show_toast, _wire_bridge,
)


class HealthPage(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        self._pending: list = []
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._svc = HealthService()
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title(tr("health.title"), tr("health.subtitle")))
        top = QHBoxLayout()
        self._gauge = Gauge("Score", 160); top.addWidget(self._gauge)
        info = QFrame(); info.setObjectName("card")
        il = QVBoxLayout(info); il.setContentsMargins(16, 14, 16, 14)
        il.addWidget(QLabel("Summary"))
        self._summary = QLabel(tr("health.summary_idle"))
        self._summary.setWordWrap(True)
        il.addWidget(self._summary)
        top.addWidget(info, 1)
        tw = QWidget(); tw.setLayout(top); outer.addWidget(tw)
        bar = QHBoxLayout()
        self._btn_scan = ScanButton(tr("health.run_scan"), page=self)
        self._btn_scan.clicked.connect(self._refresh)
        bar.addWidget(self._btn_scan); bar.addStretch()
        bw = QWidget(); bw.setLayout(bar); outer.addWidget(bw)
        outer.addWidget(make_section("Issues"))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Code", "Severity", "Title", "Detail"])
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

    def retranslate(self) -> None:
        self._btn_scan._label.setText(tr("health.run_scan"))
        self._summary.setText(tr("health.summary_idle"))

    def _refresh(self) -> None:
        _set_status(self, "Scanning system health...")

        def on_done(r):
            self._bridge.post(self._render, r)

        def on_error(exc):
            self._bridge.post(lambda e=exc: _show_toast(self, f"Health scan failed: {e}", "error"))

        self._btn_scan.start(self._runner, fn=self._svc.run,
                             bridge=self._bridge,
                             name="health-scan",
                             on_done=on_done, on_error=on_error)

    def _render(self, r) -> None:
        score = r.score
        grade = r.grade
        self._gauge.set_value(score)
        crit = sum(1 for i in r.issues if i.severity >= 3)
        warn = sum(1 for i in r.issues if i.severity == 2)
        self._summary.setText(
            f"<b>{score}/100 (grade {grade})</b><br>"
            f"{len(r.issues)} issues: {crit} critical, {warn} warning."
        )
        self._tbl.setRowCount(len(r.issues))
        for i, p in enumerate(r.issues):
            self._tbl.setItem(i, 0, QTableWidgetItem(p.code))
            self._tbl.setItem(i, 1, QTableWidgetItem(p.severity.label.upper()))
            self._tbl.setItem(i, 2, QTableWidgetItem(p.title))
            self._tbl.setItem(i, 3, QTableWidgetItem(p.detail[:120]))