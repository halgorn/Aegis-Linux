"""Monitor page — live CPU/RAM/disk/net gauges + line charts + top procs."""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.collectors import procfs as proc_col
from aegis.services.alerts import AlertThresholds, AlertWatcher
from aegis.services.monitor_service import MonitorService
from aegis.ui.widgets.qt import Gauge, make_section, make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _make_chart, _runner, _run_scan, _show_toast, _wire_bridge,
)


class MonitorPage(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        self._pending: list = []
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._svc = MonitorService()
        self._samples: list = []
        self._alerts = AlertWatcher(AlertThresholds(), _show_toast.bind_to(self) if hasattr(_show_toast, "bind_to") else _show_toast)
        # bind_to doesn't exist; use a thin lambda that defers to _show_toast(self, ...)
        self._alerts = AlertWatcher(AlertThresholds(), lambda msg, kind: _show_toast(self, msg, kind))
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title("Monitor", "Live CPU, memory, disk and network usage."))
        gw = QHBoxLayout(); gw.setSpacing(12)
        self._g_cpu = Gauge("CPU", 110)
        self._g_ram = Gauge("RAM", 110)
        self._g_disk = Gauge("DISK", 110)
        self._g_net = Gauge("NET", 110)
        for g in (self._g_cpu, self._g_ram, self._g_disk, self._g_net):
            gw.addWidget(g)
        gw_w = QWidget(); gw_w.setLayout(gw); outer.addWidget(gw_w)
        outer.addWidget(make_section("History (last 60 s) - hover for values"))
        sw = QHBoxLayout(); sw.setSpacing(12)
        from PyQt6.QtCharts import QChartView
        self._charts: dict[str, tuple] = {}
        for key, label, color_key in (
            ("cpu", "CPU", "blue"),
            ("ram", "RAM", "mauve"),
            ("disk", "DISK", "green"),
            ("net", "NET", "cyan"),
        ):
            chart, series = _make_chart(label, color_key, capacity=60)
            self._charts[key] = (chart, series)
            view = QChartView(chart)
            view.setRenderHint(QPainter.RenderHint.Antialiasing)
            view.setMinimumHeight(110)
            box = QFrame(); box.setObjectName("card")
            bl = QVBoxLayout(box); bl.setContentsMargins(12, 8, 12, 8)
            bl.addWidget(QLabel(label))
            bl.addWidget(view, 1)
            sw.addWidget(box)
        sw_w = QWidget(); sw_w.setLayout(sw); outer.addWidget(sw_w, 1)
        outer.addWidget(make_section("Top CPU"))
        self._top = QTableWidget(0, 3)
        self._top.setHorizontalHeaderLabels(["PID", "Name", "CPU %"])
        self._top.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._top.verticalHeader().setVisible(False)
        outer.addWidget(self._top, 1)

    def on_show(self) -> None:
        self._timer.start(); self._tick()

    def on_hide(self) -> None:
        self._timer.stop()

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

    def _tick(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge,
                  name="monitor-sample",
                  fn=lambda: (self._svc.sample_once(), proc_col.list_processes(top=8)),
                  on_render=self._render)

    def _render(self, payload) -> None:
        s, procs = payload
        self._samples.append(s)
        self._samples = self._samples[-120:]
        # Fire threshold alerts (each one at most once per session).
        self._alerts.check(s)
        cpu, mem, disk = s.cpu_pct, s.mem_pct * 100, s.disk_used_pct
        net = min(100.0, (s.rx_kbps + s.tx_kbps) / 1024.0)
        self._g_cpu.set_value(cpu)
        self._g_ram.set_value(mem)
        self._g_disk.set_value(disk)
        self._g_net.set_value(net)
        for key, val in (("cpu", cpu), ("ram", mem), ("disk", disk), ("net", net)):
            chart, series = self._charts[key]
            n = series.count()
            series.append(float(n), val)
            if n >= 60:
                series.remove(0)
        self._top.setRowCount(len(procs))
        for i, p in enumerate(procs):
            self._top.setItem(i, 0, QTableWidgetItem(str(p.pid)))
            self._top.setItem(i, 1, QTableWidgetItem(p.name[:30]))
            self._top.setItem(i, 2, QTableWidgetItem(f"{p.cpu_pct:.1f}"))