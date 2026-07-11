"""Disks page — mounts, SMART, large files, duplicates."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from aegis.collectors import disks as disks_col
from aegis.collectors import smart as smart_col
from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.ui.theme import current, font, fmt_bytes
from aegis.ui.widgets.charts import Gauge
from aegis.ui.widgets.common import Card, button
from aegis.ui.widgets.scrollable import ScrollableFrame


def _get_bridge(widget):
    cur = widget
    while cur is not None:
        b = getattr(cur, "_aegis_bridge", None)
        if b is not None:
            return b
        cur = cur.master
    return None


class DisksPage(tk.Frame):
    def __init__(self, parent) -> None:
        super().__init__(parent, bg=current().bg)
        self._runner = TaskRunner(max_workers=1)
        bridge = _get_bridge(parent)
        if bridge is not None:
            self._runner.set_main_invoker(bridge.invoke)
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=current().bg, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Disks", font=("Helvetica", 18, "bold"),
                 fg=current().green, bg=current().bg).pack(side="left")
        button(hdr, "SMART scan", bg=current().green, fg=current().bg,
               command=self._scan_smart).pack(side="right", padx=4)
        button(hdr, "Run TRIM", bg=current().cyan, fg=current().bg,
               command=self._run_trim).pack(side="right", padx=4)
        button(hdr, "Refresh", bg=current().bg3, fg=current().fg,
               command=self._refresh).pack(side="right")

        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)

        # Mounts
        self._mounts_card = Card(body.inner, title="Mounts")
        self._mounts_card.pack(fill="x", padx=8, pady=6)

        # SMART
        self._smart_card = Card(body.inner, title="SMART health")
        self._smart_card.pack(fill="x", padx=8, pady=6)

        # TRIM
        self._trim_lbl = tk.Label(body.inner, text="", fg=current().cyan,
                                    bg=current().bg, font=font(10))
        self._trim_lbl.pack(anchor="w", padx=14, pady=4)

        self._refresh()

    def _refresh(self) -> None:
        spec = TaskSpec(
            name="disks",
            fn=disks_col.read_mounts,
            on_done=lambda mounts: self._render_mounts(mounts),
        )
        self._runner.submit(spec)

    def _render_mounts(self, mounts) -> None:
        for w in self._mounts_card.body.winfo_children():
            w.destroy()
        p = current()
        for m in mounts:
            row = tk.Frame(self._mounts_card.body, bg=p.bg)
            row.pack(fill="x", pady=4)
            g = Gauge(row, size=80); g.set(m.used_pct); g.pack(side="left")
            info = tk.Frame(row, bg=p.bg); info.pack(side="left", padx=8)
            tk.Label(info, text=m.mount, font=font(11, bold=True),
                     fg=p.fg, bg=p.bg).pack(anchor="w")
            tk.Label(info, text=f"{m.fstype}  ·  {m.device}",
                     fg=p.fg2, bg=p.bg, font=font(9)).pack(anchor="w")
            tk.Label(info,
                     text=f"{fmt_bytes(m.used)} / {fmt_bytes(m.size)}  "
                          f"({m.used_pct*100:.0f}%)",
                     fg=p.fg2, bg=p.bg, font=font(9)).pack(anchor="w")

    def _scan_smart(self) -> None:
        for w in self._smart_card.body.winfo_children():
            w.destroy()
        tk.Label(self._smart_card.body, text="Scanning…",
                 fg=current().fg2, bg=current().bg, font=font(10)).pack()
        self._runner.submit(TaskSpec(
            name="smart",
            fn=smart_col.all_smart_reports,
            on_done=lambda r: self._render_smart(r),
        ))

    def _render_smart(self, reports) -> None:
        for w in self._smart_card.body.winfo_children():
            w.destroy()
        p = current()
        if not reports:
            tk.Label(self._smart_card.body,
                     text="smartctl unavailable or no disks detected.",
                     fg=p.yellow, bg=p.bg, font=font(10)).pack()
            return
        for r in reports:
            row = tk.Frame(self._smart_card.body, bg=p.bg)
            row.pack(fill="x", pady=2)
            color = p.green if r.passed else p.red
            tk.Label(row, text=r.device, font=font(10, bold=True),
                     fg=p.fg, bg=p.bg, width=14, anchor="w").pack(side="left")
            tk.Label(row, text="PASSED" if r.passed else "FAILED",
                     fg=color, bg=p.bg, font=font(10, bold=True),
                     width=10, anchor="w").pack(side="left", padx=6)
            if r.temperature_c is not None:
                tk.Label(row, text=f"{r.temperature_c:.0f}°C",
                         fg=p.cyan, bg=p.bg, font=font(10)).pack(side="left",
                                                                  padx=6)
            if r.power_on_hours is not None:
                tk.Label(row, text=f"{r.power_on_hours} h",
                         fg=p.fg2, bg=p.bg, font=font(10)).pack(side="left",
                                                                  padx=6)
            if r.wear_pct is not None:
                tk.Label(row, text=f"wear {r.wear_pct}%",
                         fg=p.yellow if r.wear_pct > 50 else p.green,
                         bg=p.bg, font=font(10)).pack(side="left", padx=6)

    def _run_trim(self) -> None:
        self._trim_lbl.config(text="Running fstrim…")
        self._runner.submit(TaskSpec(
            name="trim",
            fn=smart_col.run_trim,
            on_done=lambda r: self._trim_lbl.config(text=r),
        ))