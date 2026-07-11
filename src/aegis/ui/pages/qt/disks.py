"""Disks page — filesystems + SMART status."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHeaderView, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from aegis.services.disks_service import scan as scan_disks
from aegis.ui.theme import fmt_bytes
from aegis.ui.widgets.qt import make_section, make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _run_scan, _wire_bridge,
)


class DisksPage(QWidget):
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
        outer.addWidget(make_title("Disks", "Filesystems and SMART status."))
        outer.addWidget(make_section("Filesystems"))
        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(["Mount", "Device", "Used", "Total", "Use %"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        outer.addWidget(self._tbl, 1)
        outer.addWidget(make_section("SMART"))
        self._smart = QTextEdit(); self._smart.setReadOnly(True)
        outer.addWidget(self._smart, 1)

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
                  name="disks-scan", fn=scan_disks, on_render=self._render)

    def _render(self, r) -> None:
        filesystems = r.filesystems
        self._tbl.setRowCount(len(filesystems))
        for i, fs in enumerate(filesystems):
            self._tbl.setItem(i, 0, QTableWidgetItem(fs["mount"]))
            self._tbl.setItem(i, 1, QTableWidgetItem(fs["device"]))
            self._tbl.setItem(i, 2, QTableWidgetItem(fmt_bytes(fs["used"])))
            self._tbl.setItem(i, 3, QTableWidgetItem(fmt_bytes(fs["total"])))
            self._tbl.setItem(i, 4, QTableWidgetItem(f"{fs['percent']:.0f}%"))
        if r.smart:
            txt = "\n".join(f"* {s.get('device', '?')}" for s in r.smart)
        else:
            txt = "SMART data unavailable (install smartmontools or run as root)."
        self._smart.setPlainText(txt)