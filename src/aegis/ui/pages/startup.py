"""Startup manager page — systemd + autostart + cron."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.collectors import startup as st_col
from aegis.core.concurrency import TaskRunner, TaskSpec
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


class StartupPage(tk.Frame):
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
        tk.Label(hdr, text="Startup", font=("Helvetica", 18, "bold"),
                 fg=current().mauve, bg=current().bg).pack(side="left")
        button(hdr, "Refresh", bg=current().bg3, fg=current().fg,
               command=self._refresh).pack(side="right")

        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)

        for title in ("systemd (system)", "systemd (user)",
                       "Autostart (.desktop)", "Cron (user)"):
            card = Card(body.inner, title=title)
            card.pack(fill="x", padx=8, pady=6)
            tree = ttk.Treeview(card.body, columns=("state", "name", "info"),
                                 show="headings", height=8)
            tree.heading("state", text="State")
            tree.heading("name", text="Name")
            tree.heading("info", text="Command / File")
            tree.column("state", width=80)
            tree.column("name", width=300)
            tree.column("info", width=520)
            vsb = ttk.Scrollbar(card.body, orient="vertical",
                                 command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            setattr(self, "_tree_" + title.split()[0].replace("(", "").replace(")", ""),
                    tree)
        self._refresh()

    def _refresh(self) -> None:
        spec = TaskSpec(
            name="startup",
            fn=lambda: (st_col.systemd_system_enabled(),
                        st_col.systemd_user_enabled(),
                        st_col.autostart_desktop_entries(),
                        st_col.cron_jobs()),
            on_done=lambda r: self._render(*r),
        )
        self._runner.submit(spec)

    def _render(self, sys_user, sys_system, autostart, cron) -> None:
        p = current()
        for tree, items, src in (
            (self._tree_systemd, sys_system, "system"),
            (self._tree_systemd, sys_user, "user"),  # second tree for user
            (self._tree_Autostart, autostart, "auto"),
            (self._tree_Cron, cron, "cron"),
        ):
            for iid in tree.get_children():
                tree.delete(iid)
        # systemd
        for tree, items in (
            (self._tree_systemd, sys_system),
            (getattr(self, "_tree_user", None) or self._tree_systemd, sys_user),
        ):
            for iid in tree.get_children():
                tree.delete(iid)
            for e in items:
                state = "● on" if e.enabled else "○ off"
                tree.insert("", "end",
                            values=(state, e.name, e.command or e.file))

        for e in autostart:
            self._tree_Autostart.insert(
                "", "end",
                values=("● on" if e.enabled else "○ off", e.name,
                        e.command[:80] or e.file),
            )
        for e in cron:
            self._tree_Cron.insert(
                "", "end",
                values=("● on", e.name, e.command),
            )