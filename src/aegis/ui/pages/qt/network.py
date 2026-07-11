"""Network page — interfaces + listening ports."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.services.network_service import scan as scan_network
from aegis.ui.widgets.qt import make_section, make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _run_scan, _wire_bridge,
)


class NetworkPage(QWidget):
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
        outer.addWidget(make_title("Network", "Interfaces and listening ports."))
        outer.addWidget(make_section("Interfaces"))
        self._ifaces = QTableWidget(0, 5)
        self._ifaces.setHorizontalHeaderLabels(["Name", "State", "IPv4", "IPv6", "Speed"])
        self._ifaces.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._ifaces.verticalHeader().setVisible(False)
        outer.addWidget(self._ifaces, 1)
        outer.addWidget(make_section("Listening ports"))
        self._ports = QTableWidget(0, 4)
        self._ports.setHorizontalHeaderLabels(["Port", "Proto", "Address", "Process"])
        self._ports.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._ports.verticalHeader().setVisible(False)
        outer.addWidget(self._ports, 1)

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
                  name="net-scan", fn=scan_network, on_render=self._render)

    def _render(self, r) -> None:
        ifaces = r.interfaces
        self._ifaces.setRowCount(len(ifaces))
        for i, n in enumerate(ifaces):
            self._ifaces.setItem(i, 0, QTableWidgetItem(n["name"]))
            self._ifaces.setItem(i, 1, QTableWidgetItem(n["state"]))
            self._ifaces.setItem(i, 2, QTableWidgetItem(", ".join(n["ipv4"])))
            self._ifaces.setItem(i, 3, QTableWidgetItem(", ".join(n["ipv6"])))
            self._ifaces.setItem(i, 4, QTableWidgetItem(n["speed"]))
        ports = r.listening
        self._ports.setRowCount(len(ports))
        for i, p in enumerate(ports):
            self._ports.setItem(i, 0, QTableWidgetItem(str(p["port"])))
            self._ports.setItem(i, 1, QTableWidgetItem(p["proto"]))
            self._ports.setItem(i, 2, QTableWidgetItem(p["address"]))
            self._ports.setItem(i, 3, QTableWidgetItem(p["process"][:30]))