"""Monitor page — live charts + process list + sparklines."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.domain.system import SystemSnapshot
from aegis.services.monitor_service import (
    MetricSample,
    MonitorService,
    build_snapshot,
)
from aegis.ui.theme import current, font, fmt_bytes, pct_color
from aegis.ui.widgets.charts import Gauge, Sparkline
from aegis.ui.widgets.common import Card, button
from aegis.ui.widgets.scrollable import ScrollableFrame
from aegis.ui.widgets.toast import ToastHost


def _get_bridge(widget):
    cur = widget
    while cur is not None:
        b = getattr(cur, "_aegis_bridge", None)
        if b is not None:
            return b
        cur = cur.master
    return None


class MonitorPage(tk.Frame):
    def __init__(self, parent, *, toasts: ToastHost | None = None) -> None:
        super().__init__(parent, bg=current().bg)
        self._toasts = toasts
        self._monitor = MonitorService(refresh_hz=1.0,
                                       history_seconds=600,
                                       on_sample=self._on_sample)
        self._bridge = _get_bridge(parent)
        self._snapshot = build_snapshot()
        self._build()

    def on_show(self) -> None:
        """Called when page becomes visible — start sampling."""
        self._monitor.start()

    def on_hide(self) -> None:
        """Called when page becomes hidden — stop to save CPU."""
        self._monitor.stop()

    # ── build ─────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Top row: live charts
        top = tk.Frame(self, bg=current().bg)
        top.pack(fill="x", padx=14, pady=(14, 6))
        self._cpu_card = Card(top, title="CPU")
        self._cpu_card.pack(side="left", fill="both", expand=True, padx=4)
        self._mem_card = Card(top, title="Memory")
        self._mem_card.pack(side="left", fill="both", expand=True, padx=4)
        self._net_card = Card(top, title="Network")
        self._net_card.pack(side="left", fill="both", expand=True, padx=4)
        self._gpu_card = Card(top, title="GPU")
        self._gpu_card.pack(side="left", fill="both", expand=True, padx=4)

        # Bottom: process list
        bot = Card(self, title="Top processes (RSS)")
        bot.pack(fill="both", expand=True, padx=14, pady=6)
        cols = ("pid", "name", "ram")
        self._ptree = ttk.Treeview(bot.body, columns=cols, show="headings",
                                    selectmode="browse")
        self._ptree.heading("pid", text="PID")
        self._ptree.heading("name", text="Process")
        self._ptree.heading("ram", text="RAM")
        self._ptree.column("pid", width=70, minwidth=40)
        self._ptree.column("name", width=400, minwidth=200)
        self._ptree.column("ram", width=100, minwidth=80)
        vsb = ttk.Scrollbar(bot.body, orient="vertical",
                             command=self._ptree.yview)
        self._ptree.configure(yscrollcommand=vsb.set)
        self._ptree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Render initial
        self._refresh_static()
        self._populate_procs(self._snapshot)

    # ── updates ──────────────────────────────────────────────────────

    def _on_sample(self, sample: MetricSample) -> None:
        # Called from monitor thread → marshal to main thread.
        if self._bridge is not None:
            self._bridge.invoke(self._render_sample, sample)

    def _render_sample(self, sample: MetricSample) -> None:
        p = current()
        # CPU
        for w in self._cpu_card.body.winfo_children(): w.destroy()
        g = Gauge(self._cpu_card.body, size=120); g.set(sample.cpu_pct / 100.0)
        g.pack()
        self._spark_cpu = Sparkline(self._cpu_card.body, width=240, height=50,
                                    color=pct_color(sample.cpu_pct / 100.0))
        self._spark_cpu.pack(pady=4)
        for s in self._monitor.history():
            self._spark_cpu.append(s.cpu_pct)

        # Memory
        for w in self._mem_card.body.winfo_children(): w.destroy()
        g = Gauge(self._mem_card.body, size=120); g.set(sample.mem_pct)
        g.pack()
        self._spark_mem = Sparkline(self._mem_card.body, width=240, height=50,
                                    color=pct_color(sample.mem_pct))
        self._spark_mem.pack(pady=4)
        for s in self._monitor.history():
            self._spark_mem.append(s.mem_pct * 100)

        # Network
        for w in self._net_card.body.winfo_children(): w.destroy()
        tk.Label(self._net_card.body,
                 text=f"↓ {sample.rx_kbps:.0f} KB/s",
                 fg=p.green, bg=p.bg,
                 font=("Helvetica", 14, "bold")).pack()
        tk.Label(self._net_card.body,
                 text=f"↑ {sample.tx_kbps:.0f} KB/s",
                 fg=p.yellow, bg=p.bg,
                 font=("Helvetica", 14, "bold")).pack()
        self._spark_rx = Sparkline(self._net_card.body, width=240, height=30,
                                   color=p.green, fill=False)
        self._spark_rx.pack()
        for s in self._monitor.history():
            self._spark_rx.append(s.rx_kbps)

        # GPU
        for w in self._gpu_card.body.winfo_children(): w.destroy()
        if sample.gpu_pct is not None:
            g = Gauge(self._gpu_card.body, size=120)
            g.set(sample.gpu_pct / 100.0)
            g.pack()
            if sample.gpu_temp is not None:
                tk.Label(self._gpu_card.body, text=f"{sample.gpu_temp:.0f}°C",
                         fg=p.fg2, bg=p.bg, font=font(10)).pack()
        else:
            tk.Label(self._gpu_card.body, text="(no GPU telemetry)",
                     fg=p.fg2, bg=p.bg, font=font(10)).pack()

    def _refresh_static(self) -> None:
        s = self._snapshot
        self._populate_procs(s)

    def _populate_procs(self, snap: SystemSnapshot) -> None:
        for item in self._ptree.get_children():
            self._ptree.delete(item)
        for p in snap.procs:
            self._ptree.insert("", "end",
                               values=(p.pid, p.name[:80], fmt_bytes(p.rss)))