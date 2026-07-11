"""Shared helpers for Qt pages.

Every page in ``pages/qt/`` is built from the same primitives:

* ``_bridge(host)`` — one ``WorkerBridge`` per ``MainWindow``,
  reachable by any page that needs to bounce a closure onto the GUI
  thread.
* ``_runner(host)`` — same pattern for the global ``TaskRunner``.
* ``_show_toast`` / ``_set_status`` — defer to ``MainWindow`` if the
  page is already parented to it (they no-op in tests where there's
  no ``MainWindow`` ancestor).
* ``_run_scan`` — submit a worker, bounce its result onto the bridge,
  catch errors with a toast. The page is auto-tracked for cancel-on-
  navigate when it mixes in ``CancellableScanMixin``.
* ``_wire_bridge`` — connects the bridge's ``invoke`` signal so tuples
  ``(fn, args, kwargs)`` from the worker can call back into the page.
* ``_make_chart`` — one of the four GPU-rendered monitor charts.
"""
from __future__ import annotations

import logging
import os
import platform
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtCharts import QChart, QLineSeries, QValueAxis
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from aegis.collectors import procfs as proc_col
from aegis.collectors.disks import read_mounts
from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.ui.theme import current, hex_to_rgb
from aegis.ui.widgets.qt import CancellableScanMixin, WorkerBridge

_log = logging.getLogger(__name__)


def _bridge(host: QWidget) -> WorkerBridge:
    win = host.window()
    if win is None:
        return WorkerBridge(host)
    if not hasattr(win, "_bridge"):
        win._bridge = WorkerBridge(win)  # type: ignore[attr-defined]
    return win._bridge  # type: ignore[attr-defined]


def _runner(host: QWidget) -> TaskRunner:
    win = host.window()
    if not hasattr(win, "_runner"):
        win._runner = TaskRunner()  # type: ignore[attr-defined]
    return win._runner  # type: ignore[attr-defined]


def _show_toast(parent: QWidget, text: str, kind: str = "info") -> None:
    win = parent.window()
    if hasattr(win, "show_toast"):
        win.show_toast(text, kind=kind)


def _set_status(parent: QWidget, text: str) -> None:
    win = parent.window()
    if hasattr(win, "status"):
        win.status.showMessage(text)


def _run_scan(page: QWidget, *,
              runner: TaskRunner, bridge: WorkerBridge,
              name: str, fn, on_render, track: bool = True) -> None:
    """Submit a scan task. Worker runs off-thread; on success the
    result bounces onto the GUI via ``on_render(result)``; on error
    a toast is shown. Tracks the TaskSpec on the page (when
    ``track=True`` and the page mixes in ``CancellableScanMixin``)
    so navigating away cancels it.
    """
    def _done(result):
        bridge.post(on_render, result)

    def _err(exc):
        bridge.post(lambda e=exc: _show_toast(
            page, f"{name} failed: {e}", "error"))

    if track and isinstance(page, CancellableScanMixin):
        spec = TaskSpec(name=name, fn=fn, on_done=_done, on_error=_err)
        page._track(spec)
        orig_done, orig_err = _done, _err

        def _done_untrack(result):
            page._untrack(spec)
            orig_done(result)

        def _err_untrack(exc):
            page._untrack(spec)
            orig_err(exc)

        spec = TaskSpec(name=name, fn=fn,
                        on_done=_done_untrack, on_error=_err_untrack)
    else:
        spec = TaskSpec(name=name, fn=fn, on_done=_done, on_error=_err)
    runner.submit(spec)


def _wire_bridge(page: QWidget) -> None:
    """Hook the page's WorkerBridge to dispatch tuple payloads."""
    win = page.window()
    b = getattr(win, "_bridge", None)
    if b is None:
        return

    def _dispatch(t):
        if isinstance(t, tuple) and len(t) == 3:
            fn, args, kwargs = t
            try:
                fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                _log.warning("%s invoke failed: %s",
                             page.__class__.__name__, e)
                _show_toast(page, f"Render failed: {e}", "error")

    b.invoke.connect(_dispatch)


def _make_chart(label: str, color_key: str, *, capacity: int = 60):
    """Build a (chart, series) for one of the Monitor metrics."""
    pal = current()
    series = QLineSeries()
    series.setName(label)
    pen = QPen(QColor(*hex_to_rgb(key=color_key)), 2)
    series.setPen(pen)

    chart = QChart()
    chart.addSeries(series)
    chart.setTitle("")
    chart.legend().hide()
    chart.setBackgroundRoundness(6)
    chart.setBackgroundBrush(QColor(*hex_to_rgb(key="bg2")))
    chart.setPlotAreaBackgroundBrush(QColor(*hex_to_rgb(key="bg3")))
    chart.setPlotAreaBackgroundVisible(True)
    ax = QValueAxis(); ax.setRange(0, 100); ax.setLabelFormat("%d%%")
    ax.setLabelsVisible(False); ax.setGridLineColor(QColor(*hex_to_rgb(key="bg4")))
    ay = QValueAxis(); ay.setRange(0, capacity); ay.setLabelsVisible(False)
    chart.addAxis(ax, Qt.AlignmentFlag.AlignLeft)
    chart.addAxis(ay, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(ax); series.attachAxis(ay)
    return chart, series


def _read_os_release() -> str:
    try:
        txt = Path("/etc/os-release").read_text()
        for line in txt.splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


def dashboard_snapshot() -> dict:
    """Snapshot for the Dashboard page. Runs on a worker thread."""
    cpu = proc_col.read_cpu_sample()
    mem = proc_col.read_meminfo()
    mounts = read_mounts()
    root = next((m for m in mounts if m.mount == "/"),
                mounts[0] if mounts else None)
    bo = time.time() - proc_col.read_uptime_s()
    up_secs = int(time.time() - bo)
    days, rem = divmod(up_secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    return {
        "cpu_pct": cpu.avg_pct,
        "ram_pct": mem.used_pct * 100,
        "ram_used": mem.used,
        "ram_total": mem.total,
        "disk_pct": (root.used / root.size * 100) if root and root.size else 0,
        "disk_used": root.used if root else 0,
        "disk_total": root.size if root else 0,
        "uptime": f"{days}d {hours}h {mins}m",
        "distro": _read_os_release(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "cpu_model": (platform.processor() or "unknown")[:60],
        "cpu_cores": os.cpu_count() or 0,
    }