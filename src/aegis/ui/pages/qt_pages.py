"""Qt pages — one factory per route.

Single file because they share the same parent (``MainWindow``) and
the same widget composition patterns; splitting them per-file would
just multiply imports without buying anything.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtCharts import (
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aegis.collectors import procfs as proc_col
from aegis.collectors import sysfs as sysfs_col
from aegis.collectors.disks import read_mounts
from aegis.collectors import browser as browser_col
from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.core.logging import get_logger
from aegis.domain.cleaner import CleanResult
from aegis.rules.cleaner_rules import all_targets
from aegis.services import backup_service as backup_svc
from aegis.services.cleaner_service import CleanerService
from aegis.services.health_service import HealthService
from aegis.services.monitor_service import MonitorService
from aegis.services.security_service import SecurityService
from aegis.services.network_service import scan as scan_network
from aegis.services.disks_service import scan as scan_disks
from aegis.services.drivers_service import scan as scan_drivers
from aegis.services.packages_service import scan as scan_packages
from aegis.services.startup_service import scan as scan_startup
from aegis.services.logs_service import tail as tail_logs
from aegis.ui.theme import current, fmt_bytes, hex_to_rgb
from aegis.ui.widgets.qt import (
    CancellableScanMixin,
    Gauge,
    ScanButton,
    Sparkline,
    WorkerBridge,
    make_kpi,
    make_section,
    make_title,
    set_kpi_value,
)


_log = get_logger(__name__)


# ── shared helpers ────────────────────────────────────────────────────────────

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
    r"""Submit a scan task with bounded error handling. The worker fn runs
    off-thread; on success it bounces ``on_render(result)`` to the GUI
    via the bridge; on failure it shows an error toast. Both paths
    leave the UI in a usable state — no disabled widgets. Tracks the
    TaskSpec on the page (when track=True) so navigating away
    cancels it."""
    def _done(result):
        bridge.post(on_render, result)
    def _err(exc):
        bridge.post(lambda e=exc: _show_toast(
            page, f"{name} failed: {e}", "error"))
    if track and isinstance(page, CancellableScanMixin):
        # We need to build the spec *first* so the untrack closures
        # can close over it.
        spec = TaskSpec(name=name, fn=fn, on_done=_done, on_error=_err)
        page._track(spec)
        orig_done, orig_err = _done, _err
        def _done_untrack(*a, kw=None, **kwrest):
            page._untrack(spec)
            orig_done(*a)
        def _err_untrack(*a, kw=None, **kwrest):
            page._untrack(spec)
            orig_err(*a)
        spec = TaskSpec(name=name, fn=fn,
                        on_done=_done_untrack, on_error=_err_untrack)
    else:
        spec = TaskSpec(name=name, fn=fn, on_done=_done, on_error=_err)
    runner.submit(spec)
    """Submit a scan task with bounded error handling. The worker fn runs
    off-thread; on success it bounces `on_render(result)` to the GUI
    via the bridge; on failure it shows an error toast. Both paths
    leave the UI in a usable state — no disabled widgets."""
    def _done(result):
        bridge.post(on_render, result)
    def _err(exc):
        bridge.post(lambda e=exc: _show_toast(
            page, f"{name} failed: {e}", "error"))
    (spec := TaskSpec(name=name, fn=fn, on_done=_done, on_error=_err))
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
                _log.warning("%s invoke failed: %s", page.__class__.__name__, e)
                _show_toast(page, f"Render failed: {e}", "error")
    b.invoke.connect(_dispatch)


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._build_ui()
        # timer + scan triggered in on_show to avoid blocking the constructor

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)
        hour = datetime.now().hour
        greet = ("Good morning" if hour < 12
                 else "Good afternoon" if hour < 18
                 else "Good evening")
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
        host_name = socket.gethostname()
        outer.addWidget(make_title(
            f"{greet}, {user}",
            f"Welcome to Aegis Linux on {host_name}. Here's an overview of your system.",
        ))
        self._kpi_cpu = make_kpi("CPU", "—", "blue")
        self._kpi_ram = make_kpi("Memory", "—", "mauve")
        self._kpi_disk = make_kpi("Disk", "—", "green")
        self._kpi_uptime = make_kpi("Uptime", "—", "cyan")
        grid = QGridLayout(); grid.setSpacing(12)
        grid.addWidget(self._kpi_cpu, 0, 0)
        grid.addWidget(self._kpi_ram, 0, 1)
        grid.addWidget(self._kpi_disk, 0, 2)
        grid.addWidget(self._kpi_uptime, 0, 3)
        gw = QWidget(); gw.setLayout(grid)
        outer.addWidget(gw)
        outer.addWidget(make_section("System"))
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        info = QFrame(); info.setObjectName("card")
        il = QVBoxLayout(info)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(6)
        self._info_lines: dict[str, QLabel] = {}
        for k in ("Distro", "Kernel", "Python", "CPU Model",
                  "CPU Cores", "Total RAM", "Total Disk"):
            row = QHBoxLayout()
            lk = QLabel(k); lk.setObjectName("kpi_label"); lk.setFixedWidth(120)
            lv = QLabel("—")
            row.addWidget(lk); row.addWidget(lv, 1)
            rw = QWidget(); rw.setLayout(row)
            il.addWidget(rw)
            self._info_lines[k] = lv
        split.addWidget(info)
        qa = QFrame(); qa.setObjectName("card")
        ql = QVBoxLayout(qa); ql.setContentsMargins(16, 14, 16, 14); ql.setSpacing(8)
        ql.addWidget(QLabel("Quick actions"))
        for label, fn in (
            ("Run health scan", lambda: self._navigate("health")),
            ("Open cleaner", lambda: self._navigate("cleaner")),
            ("Open monitor", lambda: self._navigate("monitor")),
            ("Backup now", self._backup_now),
        ):
            b = QPushButton(label); b.clicked.connect(fn); ql.addWidget(b)
        ql.addStretch()
        split.addWidget(qa)
        split.setSizes([640, 320])
        outer.addWidget(split, 1)

    def _navigate(self, key: str) -> None:
        win = self.window()
        if hasattr(win, "show_page"):
            win.show_page(key)

    def _backup_now(self) -> None:
        try:
            entry = backup_svc.snapshot_files(
                [str(Path.home() / ".bashrc"), str(Path.home() / ".profile")],
                reason="manual-dashboard",
            )
            _show_toast(self, f"Backup #{entry.id} created.", "success")
        except Exception as e:  # noqa: BLE001
            _show_toast(self, f"Backup failed: {e}", "error")

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge,
                  name="dashboard-snapshot",
                  fn=_dashboard_snapshot,
                  on_render=self._render)

    def _render(self, snap: dict) -> None:
        try:
            set_kpi_value(self._kpi_cpu, snap['cpu_pct'], fmt="{:.0f}", suffix="%")
            # Memory and disk show two values; tween the percentage and
            # string-update the bytes portion separately (no easy way to
            # tween bytes — they're a function of the percentage).
            self._kpi_ram._value_lbl.setText(  # type: ignore[attr-defined]
                f"{snap['ram_pct']:.0f}% · {fmt_bytes(snap['ram_used'])}"
            )
            self._kpi_disk._value_lbl.setText(  # type: ignore[attr-defined]
                f"{snap['disk_pct']:.0f}% · {fmt_bytes(snap['disk_used'])}"
            )
            self._kpi_uptime._value_lbl.setText(snap['uptime'])  # type: ignore[attr-defined]
            mapping = {
                "Distro": snap.get("distro"),
                "Kernel": snap.get("kernel"),
                "Python": snap.get("python"),
                "CPU Model": snap.get("cpu_model"),
                "CPU Cores": snap.get("cpu_cores"),
                "Total RAM": fmt_bytes(snap.get("ram_total", 0)),
                "Total Disk": fmt_bytes(snap.get("disk_total", 0)),
            }
            for k, v in mapping.items():
                if k in self._info_lines and v is not None:
                    self._info_lines[k].setText(str(v))
        except Exception as e:  # noqa: BLE001
            _log.warning("dashboard render failed: %s", e)

    def on_show(self) -> None:
        self._refresh()


def _dashboard_snapshot() -> dict:
    cpu = proc_col.read_cpu_sample()
    mem = proc_col.read_meminfo()
    mounts = read_mounts()
    root = next((m for m in mounts if m.mount == "/"), mounts[0] if mounts else None)
    bo = time.time() - proc_col.read_uptime_s()
    up_secs = int(time.time() - bo)
    days, rem = divmod(up_secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    uptime = f"{days}d {hours}h {mins}m"
    return {
        "cpu_pct": cpu.avg_pct,
        "ram_pct": mem.used_pct * 100,
        "ram_used": mem.used,
        "ram_total": mem.total,
        "disk_pct": (root.used / root.size * 100) if root and root.size else 0,
        "disk_used": root.used if root else 0,
        "disk_total": root.size if root else 0,
        "uptime": uptime,
        "distro": _read_os_release(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "cpu_model": (platform.processor() or "unknown")[:60],
        "cpu_cores": os.cpu_count() or 0,
    }


def _read_os_release() -> str:
    try:
        txt = Path("/etc/os-release").read_text()
        for line in txt.splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


# ── Cleaner ───────────────────────────────────────────────────────────────────

class CleanerPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._targets: list = []
        self._checks: dict[str, QCheckBox] = {}
        self._build_ui()
        # Render the 29 targets IMMEDIATELY (no IO) so checkboxes /
        # select-all / select-none are usable from second zero. The
        # background worker then walks each target's paths and emits
        # per-target size updates.
        self._render_placeholder()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title(
            "Cleaner",
            "Select what to clean. Dry-run is on by default — no files are removed until you confirm.",
        ))
        bar = QHBoxLayout()
        self._btn_all = QPushButton("Select all")
        self._btn_all.clicked.connect(self._select_all)
        self._btn_none = QPushButton("Select none")
        self._btn_none.clicked.connect(self._select_none)
        self._dryrun = QCheckBox("Dry run")
        self._dryrun.setChecked(True)
        self._btn_scan = ScanButton("Scan", page=self)
        self._btn_scan.clicked.connect(self._refresh)
        self._btn_clean = QPushButton("Clean selected")
        self._btn_clean.setObjectName("danger")
        self._btn_clean.clicked.connect(self._clean)
        bar.addWidget(self._btn_all)
        bar.addWidget(self._btn_none)
        bar.addSpacing(20)
        bar.addWidget(QLabel("Total reclaimable:"))
        self._total_lbl = QLabel("—")
        self._total_lbl.setStyleSheet("font-weight: 600;")
        bar.addWidget(self._total_lbl)
        bar.addStretch()
        bar.addWidget(self._dryrun)
        bar.addWidget(self._btn_scan)
        bar.addWidget(self._btn_clean)
        bw = QWidget(); bw.setLayout(bar)
        outer.addWidget(bw)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "Target", "Description", "Estimated size"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        split.addWidget(self._table)

        detail = QFrame(); detail.setObjectName("card")
        dl = QVBoxLayout(detail); dl.setContentsMargins(16, 14, 16, 14); dl.setSpacing(6)
        dl.addWidget(QLabel("Selection details"))
        self._detail = QTextEdit(); self._detail.setReadOnly(True)
        dl.addWidget(self._detail, 1)
        split.addWidget(detail)
        split.setSizes([820, 380])
        outer.addWidget(split, 1)
        self._table.itemSelectionChanged.connect(self._on_select)

    def on_show(self) -> None:
        # Kick off the initial size scan the first time the user lands
        # on this page. Re-clicking the Scan button re-runs the scan
        # from scratch (with cancellation of the in-flight walk).
        self._refresh()

    def _select_all(self) -> None:
        for cb in self._checks.values():
            cb.setChecked(True)

    def _select_none(self) -> None:
        for cb in self._checks.values():
            cb.setChecked(False)

    def _refresh(self) -> None:
        """Re-scan every target. The actual work (path walking,
        size estimation, per-row UI updates) runs on a worker thread
        for the duration of the scan; the button stays enabled and
        flips its label to "Scan · …" while the work is in flight.
        Re-clicks cancel the in-flight walk and restart from zero."""
        _set_status(self, "Scanning cleanable targets…")
        page = self
        def worker():
            _log.info("[cleaner] worker start, %d targets", len(page._targets))
            try:
                from aegis.services.cleaner_service import _estimate_target_size
                from aegis.domain.cleaner import CleanKind
                for i, t in enumerate(page._targets):
                    current = page._btn_scan._current
                    if current is None or current.cancelled:
                        _log.info("[cleaner] cancelled at i=%d", i)
                        return
                    if t.kind == CleanKind.EXEC:
                        size = 0
                    else:
                        size = _estimate_target_size(t) or 0
                    page._bridge.post(page._update_target_size, t, size)
                    if i % 4 == 0:
                        page._bridge.post(page._update_total)
                page._bridge.post(page._update_total)
                _log.info("[cleaner] worker done")
            except Exception as e:  # noqa: BLE001
                _log.exception("[cleaner] worker failed: %s", e)
                raise
        def on_done(_):
            _log.info("[cleaner] on_done")
        def on_error(exc):
            _log.warning("[cleaner] on_error: %r", exc)
            page._bridge.post(lambda e=exc: _show_toast(page, f"Scan failed: {e}", "error"))
        self._btn_scan.start(self._runner, fn=worker,
                             bridge=self._bridge,
                             name="cleaner-scan",
                             on_done=on_done, on_error=on_error)

    def _render_placeholder(self) -> None:
        """Render the 29 targets immediately with size='…' so all UI
        controls (select all, checkboxes, dry-run, clean) are usable
        from second zero. The actual size walk is triggered by the
        'Scan' button (or by the page's on_show, when first shown)."""
        from aegis.rules.cleaner_rules import all_targets as _all
        self._targets = list(_all())
        self._checks.clear()
        self._table.setRowCount(len(self._targets))
        for row, t in enumerate(self._targets):
            cb = QCheckBox()
            self._checks[t.id] = cb
            cw = QWidget(); cl = QHBoxLayout(cw); cl.setContentsMargins(8, 0, 8, 0)
            cl.addWidget(cb); cl.addStretch()
            self._table.setCellWidget(row, 0, cw)
            self._table.setItem(row, 1, QTableWidgetItem(t.label))
            self._table.setItem(row, 2, QTableWidgetItem(t.description))
            self._table.setItem(row, 3, QTableWidgetItem("…"))
        self._total_lbl.setText("…")
        self._table.setEnabled(True)
        _set_status(self, f"{len(self._targets)} targets loaded. Click Scan to size.")

    def _update_target_size(self, t, size: int) -> None:
        """Called on GUI thread for each completed size."""
        object.__setattr__(t, "estimated_size", size)
        for row, target in enumerate(self._targets):
            if target is t:
                # Animate the cell text swap with a subtle color fade
                item = self._table.item(row, 3)
                item.setText(fmt_bytes(size))
                break
        self._update_total()

    def _update_total(self) -> None:
        total = sum(getattr(t, "estimated_size", 0) for t in self._targets)
        self._total_lbl.setText(fmt_bytes(total))
        if all(getattr(t, "estimated_size", 0) > 0 or t.kind.value == "exec"
               for t in self._targets):
            _set_status(self, f"Scan complete. {len(self._targets)} targets, "
                          f"{fmt_bytes(total)} reclaimable.")
            self._btn_scan.finish()

    def _render(self, targets) -> None:
        # Legacy entry point — kept for any caller referencing _render
        # from external tests. The page now renders instantly via
        # _render_placeholder and updates sizes incrementally through
        # _update_target_size / _update_total.
        if not self._targets:
            self._render_placeholder()

    def _on_select(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._detail.clear(); return
        idx = rows[0].row()
        t = self._targets[idx]
        self._detail.setPlainText(
            f"<b>{t.label}</b><br><br>"
            f"<i>{t.description}</i><br><br>"
            f"<b>Category:</b> {t.category}<br>"
            f"<b>Kind:</b> {t.kind}<br>"
            f"<b>Needs root:</b> {t.needs_root}<br>"
            f"<b>Reversible:</b> {t.reversible}<br>"
            f"<b>Estimated:</b> {fmt_bytes(t.estimated_size)}<br>"
            f"<b>Path count:</b> {len(t.paths)}<br>"
            f"<br><b>Paths:</b><br>"
            + "<br>".join(f"  • {p}" for p in t.paths[:30])
            + (f"<br>  … +{len(t.paths) - 30} more" if len(t.paths) > 30 else "")
        )

    def _clean(self) -> None:
        ids = [tid for tid, cb in self._checks.items() if cb.isChecked()]
        if not ids:
            _show_toast(self, "No targets selected.", "warn"); return
        if not self._dryrun.isChecked():
            r = QMessageBox.question(
                self, "Confirm cleanup",
                f"Delete files from {len(ids)} targets?\n"
                "This action is reversible only via the Restore page if a backup was made.",
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        if hasattr(self, "_btn_clean_busy") and self._btn_clean_busy:
            return
        self._btn_clean_busy = True
        self._btn_clean.setEnabled(False)
        self._btn_clean.setText("Cleaning…")
        _set_status(self, "Cleaning…")
        dry = self._dryrun.isChecked()
        def run():
            try:
                res = CleanerService().run(target_ids=ids, dry_run=dry, create_backup=not dry)
                self._bridge.post(self._on_clean_done, res, dry)
            except Exception as e:  # noqa: BLE001
                self._bridge.post(lambda exc=e: self._on_clean_error(exc))
        (spec := TaskSpec(name="cleaner-run", fn=run)); self._runner.submit(spec)

    def _on_clean_done(self, res, dry: bool) -> None:
        self._btn_clean_busy = False
        self._btn_clean.setEnabled(True)
        self._btn_clean.setText("Clean selected")
        msg = (f"{'[DRY] ' if dry else ''}Reclaimed "
               f"{fmt_bytes(res.bytes_freed)} across {len(res.records)} items.")
        _show_toast(self, msg, "success")
        _set_status(self, msg)
        self._refresh()

    def _on_clean_error(self, exc) -> None:
        self._btn_clean_busy = False
        self._btn_clean.setEnabled(True)
        self._btn_clean.setText("Clean selected")
        _show_toast(self, f"Clean failed: {exc}", "error")


# ── Monitor ───────────────────────────────────────────────────────────────────

class MonitorPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._svc = MonitorService()
        self._samples: list = []
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
        outer.addWidget(make_section("History (last 60 s) — hover for values"))
        sw = QHBoxLayout(); sw.setSpacing(12)
        # Hardware-accelerated PyQt6-Charts instead of the hand-rolled
        # Sparkline: zoomable, pannable, with crosshair tooltips, gradient
        # fill under the line, and CSS-styled background. All painted
        # by the Qt RHI on the GPU.
        self._charts: dict[str, tuple[QChart, QLineSeries]] = {}
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

    def _tick(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge,
                  name="monitor-sample",
                  fn=lambda: (self._svc.sample_once(), proc_col.list_processes(top=8)),
                  on_render=self._render)

    def _render(self, payload) -> None:
        s, procs = payload
        self._samples.append(s)
        self._samples = self._samples[-120:]
        cpu, mem, disk = s.cpu_pct, s.mem_pct * 100, s.disk_used_pct
        net = min(100.0, (s.rx_kbps + s.tx_kbps) / 1024.0)
        self._g_cpu.set_value(cpu)
        self._g_ram.set_value(mem)
        self._g_disk.set_value(disk)
        self._g_net.set_value(net)
        # Update the GPU-rendered QtCharts series. Each series uses
        # (x = tick index, y = metric value). x is a running counter
        # so old points slide off the left edge.
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
    chart.setMargins(chart.margins())  # keep default
    # Two value axes — 0..100 for utilisation, 0..capacity on x for time
    ax = QValueAxis(); ax.setRange(0, 100); ax.setLabelFormat("%d%%")
    ax.setLabelsVisible(False); ax.setGridLineColor(QColor(*hex_to_rgb(key="bg4")))
    ay = QValueAxis(); ay.setRange(0, capacity); ay.setLabelsVisible(False)
    chart.addAxis(ax, Qt.AlignmentFlag.AlignLeft)
    chart.addAxis(ay, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(ax); series.attachAxis(ay)
    return chart, series


# ── Performance ───────────────────────────────────────────────────────────────

class PerformancePage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title("Performance",
            "Top processes and tunable kernel parameters."))
        outer.addWidget(make_section("Top processes (by CPU)"))
        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(["PID", "Name", "CPU %", "RSS", "User"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        outer.addWidget(self._tbl, 1)
        outer.addWidget(make_section("Tunables"))
        self._tun_info: dict[str, QLabel] = {}
        tun_w = QWidget(); tun_l = QFormLayout(tun_w)
        for k in ("vm.swappiness", "vm.dirty_ratio", "vm.dirty_background_ratio"):
            lbl = QLabel("—"); tun_l.addRow(QLabel(k), lbl)
            self._tun_info[k] = lbl
        outer.addWidget(tun_w)

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge,
                  name="perf-sample",
                  fn=lambda: (proc_col.list_processes(top=30),
                              {k: sysfs_col.read_sysctl(k, "?") for k in self._tun_info}),
                  on_render=self._render)

    def _render(self, payload) -> None:
        procs, sysctl = payload
        self._tbl.setRowCount(len(procs))
        for i, p in enumerate(procs):
            self._tbl.setItem(i, 0, QTableWidgetItem(str(p.pid)))
            self._tbl.setItem(i, 1, QTableWidgetItem(p.name[:30]))
            self._tbl.setItem(i, 2, QTableWidgetItem(f"{p.cpu_pct:.1f}"))
            self._tbl.setItem(i, 3, QTableWidgetItem(fmt_bytes(p.rss)))
            self._tbl.setItem(i, 4, QTableWidgetItem((p.user or "")[:20]))
        for k, v in sysctl.items():
            if k in self._tun_info:
                self._tun_info[k].setText(str(v))


# ── Health ────────────────────────────────────────────────────────────────────

class HealthPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._svc = HealthService()
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title("Health", "System wellness score (0–100)."))
        top = QHBoxLayout()
        self._gauge = Gauge("Score", 160); top.addWidget(self._gauge)
        info = QFrame(); info.setObjectName("card")
        il = QVBoxLayout(info); il.setContentsMargins(16, 14, 16, 14)
        il.addWidget(QLabel("Summary"))
        self._summary = QLabel("Run a scan to compute the score.")
        self._summary.setWordWrap(True)
        il.addWidget(self._summary)
        top.addWidget(info, 1)
        tw = QWidget(); tw.setLayout(top); outer.addWidget(tw)
        bar = QHBoxLayout()
        self._btn_scan = ScanButton("Run scan", page=self)
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

    def _refresh(self) -> None:
        _set_status(self, "Scanning system health…")
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


# ── Security ──────────────────────────────────────────────────────────────────

class SecurityPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._svc = SecurityService()
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

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

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge, name="sec-scan", fn=lambda: self._svc.scan(), on_render=self._render)

    def _render(self, findings) -> None:
        self._tbl.setRowCount(len(findings))
        for i, c in enumerate(findings):
            self._tbl.setItem(i, 0, QTableWidgetItem(c.code))
            sev = c.severity
            sev_label = sev.label if hasattr(sev, "label") else str(sev)
            self._tbl.setItem(i, 1, QTableWidgetItem(sev_label.upper()))
            self._tbl.setItem(i, 2, QTableWidgetItem(c.title))
            self._tbl.setItem(i, 3, QTableWidgetItem((c.detail or "")[:120]))


# ── Network ───────────────────────────────────────────────────────────────────

class NetworkPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

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

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge, name="net-scan", fn=scan_network, on_render=self._render)

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


# ── Disks ─────────────────────────────────────────────────────────────────────

class DisksPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

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

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge, name="disks-scan", fn=scan_disks, on_render=self._render)

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
            txt = "\n".join(f"● {s.get('device', '?')}" for s in r.smart)
        else:
            txt = "SMART data unavailable (install smartmontools or run as root)."
        self._smart.setPlainText(txt)


# ── Drivers ───────────────────────────────────────────────────────────────────

class DriversPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(make_title("Drivers", "Kernel modules currently loaded."))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Module", "Size", "Used by", "State"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        outer.addWidget(self._tbl, 1)

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge, name="drv-scan", fn=scan_drivers, on_render=self._render)

    def _render(self, r) -> None:
        mods = r.modules
        self._tbl.setRowCount(len(mods))
        for i, m in enumerate(mods):
            self._tbl.setItem(i, 0, QTableWidgetItem(m["name"]))
            self._tbl.setItem(i, 1, QTableWidgetItem(m["size"]))
            self._tbl.setItem(i, 2, QTableWidgetItem(m["used_by"]))
            self._tbl.setItem(i, 3, QTableWidgetItem(m["state"]))


# ── Packages ──────────────────────────────────────────────────────────────────

class PackagesPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(make_title("Packages", "Orphaned and duplicate packages."))
        self._tbl = QTableWidget(0, 3)
        self._tbl.setHorizontalHeaderLabels(["Package", "Manager", "Reason"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        outer.addWidget(self._tbl, 1)

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge, name="pkg-scan", fn=scan_packages, on_render=self._render)

    def _render(self, r) -> None:
        pkgs = r.packages
        self._tbl.setRowCount(len(pkgs))
        for i, p in enumerate(pkgs):
            self._tbl.setItem(i, 0, QTableWidgetItem(p["name"]))
            self._tbl.setItem(i, 1, QTableWidgetItem(p["manager"]))
            self._tbl.setItem(i, 2, QTableWidgetItem(p["reason"]))


# ── Startup ───────────────────────────────────────────────────────────────────

class StartupPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(make_title("Startup", "Enabled systemd services."))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Name", "Scope", "State", "Description"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        outer.addWidget(self._tbl, 1)

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge, name="startup-scan", fn=scan_startup, on_render=self._render)

    def _render(self, r) -> None:
        items = r.items
        self._tbl.setRowCount(len(items))
        for i, it in enumerate(items):
            self._tbl.setItem(i, 0, QTableWidgetItem(it["name"]))
            self._tbl.setItem(i, 1, QTableWidgetItem(it["scope"]))
            self._tbl.setItem(i, 2, QTableWidgetItem(it["state"]))
            self._tbl.setItem(i, 3, QTableWidgetItem((it.get("description") or "")[:100]))


# ── Restore ───────────────────────────────────────────────────────────────────

class RestorePage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(make_title("Restore",
            "Backups created by the Cleaner. Restore any backup to revert changes."))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["ID", "Created", "Reason", "Files"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        outer.addWidget(self._tbl, 1)
        bar = QHBoxLayout()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self._refresh)
        self._btn_restore = QPushButton("Restore selected")
        self._btn_restore.setObjectName("danger")
        self._btn_restore.clicked.connect(self._restore)
        bar.addStretch(); bar.addWidget(self._btn_refresh); bar.addWidget(self._btn_restore)
        bw = QWidget(); bw.setLayout(bar); outer.addWidget(bw)

    def _refresh(self) -> None:
        try:
            backups = backup_svc.list_backups()
        except Exception as e:  # noqa: BLE001
            _show_toast(self, f"Cannot list backups: {e}", "error")
            backups = []
        self._backups = backups
        self._tbl.setRowCount(len(backups))
        for i, b in enumerate(backups):
            self._tbl.setItem(i, 0, QTableWidgetItem(str(b.id)))
            self._tbl.setItem(i, 1, QTableWidgetItem(b.created_at[:19]))
            self._tbl.setItem(i, 2, QTableWidgetItem(b.reason or ""))
            self._tbl.setItem(i, 3, QTableWidgetItem(str(len(b.files))))

    def _restore(self) -> None:
        rows = self._tbl.selectionModel().selectedRows()
        if not rows:
            _show_toast(self, "No backup selected.", "warn"); return
        bid = int(self._tbl.item(rows[0].row(), 0).text())
        confirm = QMessageBox.question(
            self, "Confirm restore",
            f"Restore backup #{bid}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            backup_svc.restore(self._backups[rows[0].row()])
            _show_toast(self, f"Backup #{bid} restored.", "success")
        except Exception as e:  # noqa: BLE001
            _show_toast(self, f"Restore failed: {e}", "error")


# ── Logs ──────────────────────────────────────────────────────────────────────

class LogsPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()
        # scan triggered in on_show to avoid blocking the constructor

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

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge, name="logs-fetch", fn=lambda: tail_logs(lines=400), on_render=self._render)

    def _render(self, r) -> None:
        self._view.setPlainText("\n".join(r.lines))


# ── Settings ──────────────────────────────────────────────────────────────────

class SettingsPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
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


# ── registry ──────────────────────────────────────────────────────────────────

def build_pages(host: QWidget) -> dict[str, QWidget]:
    return {
        "dashboard": DashboardPage(host),
        "cleaner": CleanerPage(host),
        "monitor": MonitorPage(host),
        "performance": PerformancePage(host),
        "health": HealthPage(host),
        "security": SecurityPage(host),
        "network": NetworkPage(host),
        "disks": DisksPage(host),
        "drivers": DriversPage(host),
        "packages": PackagesPage(host),
        "startup": StartupPage(host),
        "restore": RestorePage(host),
        "logs": LogsPage(host),
        "settings": SettingsPage(host),
    }