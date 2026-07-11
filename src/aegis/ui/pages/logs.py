"""Logs page — systemd journal recent + journal disk usage."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.collectors import logs as logs_col
from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.ui.theme import current, font
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


class LogsPage(tk.Frame):
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
        tk.Label(hdr, text="Logs", font=("Helvetica", 18, "bold"),
                 fg=current().cyan, bg=current().bg).pack(side="left")
        self._disk_lbl = tk.Label(hdr, text="—", fg=current().fg2,
                                    bg=current().bg, font=font(10))
        self._disk_lbl.pack(side="left", padx=12)
        button(hdr, "Refresh", bg=current().bg3, fg=current().fg,
               command=self._refresh).pack(side="right")

        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)

        card = Card(body.inner, title="Recent (priority ≤ warning, last 24h)")
        card.pack(fill="both", expand=True, padx=8, pady=6)
        self._tree = ttk.Treeview(card.body,
                                   columns=("ts", "unit", "message"),
                                   show="headings", height=24)
        self._tree.heading("ts", text="Time")
        self._tree.heading("unit", text="Unit")
        self._tree.heading("message", text="Message")
        self._tree.column("ts", width=150, minwidth=120)
        self._tree.column("unit", width=140, minwidth=80)
        self._tree.column("message", width=600, minwidth=300)
        vsb = ttk.Scrollbar(card.body, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._refresh()

    def _refresh(self) -> None:
        self._disk_lbl.config(text=logs_col.journal_disk_usage())
        spec = TaskSpec(
            name="logs",
            fn=lambda: logs_col.journal_recent(priority="warning", limit=300),
            on_done=lambda r: self._render(r),
        )
        self._runner.submit(spec)

    def _render(self, entries) -> None:
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        p = current()
        for e in entries:
            self._tree.insert("", "end",
                              values=(e.ts.strftime("%Y-%m-%d %H:%M:%S"),
                                      e.unit, e.message[:200]))