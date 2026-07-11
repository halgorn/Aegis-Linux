"""Performance page — recommendations from PerformanceService."""

from __future__ import annotations

import tkinter as tk

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.services.performance_service import PerformanceService
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


class PerformancePage(tk.Frame):
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
        tk.Label(hdr, text="Performance", font=("Helvetica", 18, "bold"),
                 fg=current().blue, bg=current().bg).pack(side="left")
        button(hdr, "Analyze", bg=current().blue, fg=current().bg,
               command=self._refresh).pack(side="right")
        self._body = ScrollableFrame(self)
        self._body.pack(fill="both", expand=True)
        self._refresh()

    def _refresh(self) -> None:
        self._runner.submit(TaskSpec(
            name="perf",
            fn=PerformanceService().recommendations,
            on_done=lambda r: self._render(r),
        ))

    def _render(self, recs) -> None:
        for w in self._body.inner.winfo_children():
            w.destroy()
        p = current()
        if not recs:
            tk.Label(self._body.inner, text="No recommendations.",
                     fg=p.fg2, bg=p.bg, font=font(11)).pack(pady=20)
            return
        for r in recs:
            accent = {"high": p.red, "medium": p.yellow, "low": p.fg2}.get(
                r.impact, p.fg)
            card = Card(self._body.inner, title=r.title, accent=accent)
            card.pack(fill="x", padx=8, pady=6)
            tk.Label(card.body, text=r.detail,
                     fg=p.fg, bg=p.bg, font=font(10),
                     wraplength=600, justify="left").pack(anchor="w")
            if r.command:
                cmd = " ".join(r.command)
                tk.Label(card.body, text=f"$ {cmd}",
                         fg=p.cyan, bg=p.bg3, font=("Courier", 10),
                         padx=8, pady=4).pack(anchor="w", pady=4, fill="x")