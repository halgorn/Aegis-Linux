"""Packages page — list installed + pending updates across managers."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.collectors.packages import all_packages, managers_available
from aegis.domain.packages import PkgManager
from aegis.ui.theme import current, font
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


class PackagesPage(tk.Frame):
    def __init__(self, parent, *, toasts: ToastHost | None = None) -> None:
        super().__init__(parent, bg=current().bg)
        self._toasts = toasts
        self._runner = TaskRunner(max_workers=1)
        bridge = _get_bridge(parent)
        if bridge is not None:
            self._runner.set_main_invoker(bridge.invoke)
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=current().bg, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Packages", font=("Helvetica", 18, "bold"),
                 fg=current().green, bg=current().bg).pack(side="left")
        self._summary_lbl = tk.Label(hdr, text="—", font=font(10),
                                      fg=current().fg2, bg=current().bg)
        self._summary_lbl.pack(side="left", padx=12)
        button(hdr, "Refresh", bg=current().bg3, fg=current().fg,
               command=self._refresh).pack(side="right")

        # Updates section
        self._updates_card = Card(self, title="Pending updates")
        self._updates_card.pack(fill="x", padx=14, pady=8)
        cols = ("mgr", "name", "available", "current")
        self._upd_tree = ttk.Treeview(
            self._updates_card.body, columns=cols, show="headings",
            selectmode="extended", height=8,
        )
        for col, label, w in (("mgr", "Manager", 90),
                              ("name", "Package", 380),
                              ("available", "Available", 160),
                              ("current", "Current", 160)):
            self._upd_tree.heading(col, text=label)
            self._upd_tree.column(col, width=w, minwidth=80)
        vsb = ttk.Scrollbar(self._updates_card.body, orient="vertical",
                             command=self._upd_tree.yview)
        self._upd_tree.configure(yscrollcommand=vsb.set)
        self._upd_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Installed section
        self._installed_card = Card(self, title="Installed packages")
        self._installed_card.pack(fill="both", expand=True, padx=14, pady=8)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        bar = tk.Frame(self._installed_card.body, bg=current().bg)
        bar.pack(fill="x")
        tk.Label(bar, text="Search:", fg=current().fg2, bg=current().bg,
                 font=font(10)).pack(side="right")
        tk.Entry(bar, textvariable=self._search_var, bg=current().bg3,
                 fg=current().fg, insertbackground=current().fg,
                 relief="flat", font=font(10), width=28).pack(side="right",
                                                              padx=6)

        self._inst_tree = ttk.Treeview(
            self._installed_card.body,
            columns=("mgr", "name", "version"), show="headings",
            selectmode="browse",
        )
        for col, label, w in (("mgr", "Manager", 90),
                              ("name", "Package", 460),
                              ("version", "Version", 200)):
            self._inst_tree.heading(col, text=label)
            self._inst_tree.column(col, width=w, minwidth=80)
        vsb2 = ttk.Scrollbar(self._installed_card.body, orient="vertical",
                              command=self._inst_tree.yview)
        self._inst_tree.configure(yscrollcommand=vsb2.set)
        self._inst_tree.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")

        self._installed: list = []
        self._refresh()

    def _refresh(self) -> None:
        spec = TaskSpec(
            name="packages",
            fn=all_packages,
            on_done=lambda s: self._render(s),
        )
        self._runner.submit(spec)

    def _render(self, summary) -> None:
        p = current()
        mgrs = [m.value for m in managers_available()]
        self._summary_lbl.config(text=f"managers: {', '.join(mgrs) or 'none'}")

        for iid in self._upd_tree.get_children():
            self._upd_tree.delete(iid)
        for u in summary.updates:
            self._upd_tree.insert(
                "", "end",
                values=(u.pkg.manager.value, u.pkg.name,
                        u.pkg.version or "—", u.pkg.available or "—"),
            )

        self._installed = list(summary.installed)
        self._filter()

    def _filter(self) -> None:
        q = self._search_var.get().lower()
        for iid in self._inst_tree.get_children():
            self._inst_tree.delete(iid)
        shown = [p for p in self._installed if q in p.name.lower()] \
            if q else self._installed
        for p in shown:
            self._inst_tree.insert(
                "", "end",
                values=(p.manager.value, p.name, p.version),
            )