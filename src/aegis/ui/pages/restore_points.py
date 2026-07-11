"""Restore Points page — list, create, restore from snapshots."""

from __future__ import annotations

import os
import tarfile
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from aegis.services import backup_service
from aegis.ui.theme import current, font
from aegis.ui.widgets.common import Card, button
from aegis.ui.widgets.scrollable import ScrollableFrame
from aegis.ui.widgets.toast import ToastHost


class RestorePointsPage(tk.Frame):
    def __init__(self, parent, *, toasts: ToastHost | None = None) -> None:
        super().__init__(parent, bg=current().bg)
        self._toasts = toasts
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=current().bg, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Restore Points", font=("Helvetica", 18, "bold"),
                 fg=current().mauve, bg=current().bg).pack(side="left")
        button(hdr, "Refresh", bg=current().bg3, fg=current().fg,
               command=self._refresh).pack(side="right")

        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)

        # New snapshot card
        new_card = Card(body.inner, title="Create restore point")
        new_card.pack(fill="x", padx=8, pady=6)
        tk.Label(new_card.body,
                 text="Select paths to snapshot. BTRFS/ZFS snapshots are planned (Fase 4).",
                 fg=current().fg2, bg=current().bg,
                 font=font(10)).pack(anchor="w")
        self._path_var = tk.StringVar(value=os.path.expanduser("~/.bash_history"))
        row = tk.Frame(new_card.body, bg=current().bg)
        row.pack(fill="x", pady=4)
        tk.Entry(row, textvariable=self._path_var, bg=current().bg3,
                 fg=current().fg, insertbackground=current().fg,
                 relief="flat", font=font(10), width=60).pack(side="left")
        button(row, "Snapshot", bg=current().mauve, fg=current().bg,
               command=self._snapshot).pack(side="left", padx=6)

        # Existing
        self._list_card = Card(body.inner, title="Existing backups")
        self._list_card.pack(fill="both", expand=True, padx=8, pady=6)
        self._tree = ttk.Treeview(self._list_card.body,
                                   columns=("when", "size", "id"),
                                   show="headings", height=12)
        self._tree.heading("when", text="Created")
        self._tree.heading("size", text="Size")
        self._tree.heading("id", text="ID")
        self._tree.column("when", width=180)
        self._tree.column("size", width=100)
        self._tree.column("id", width=520)
        vsb = ttk.Scrollbar(self._list_card.body, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bar = tk.Frame(self._list_card.body, bg=current().bg)
        bar.pack(fill="x", pady=4)
        button(bar, "Restore selected", bg=current().green, fg=current().bg,
               command=self._restore).pack(side="left", padx=4)
        button(bar, "Delete", bg=current().red, fg=current().bg,
               command=self._delete).pack(side="left", padx=4)

        self._refresh()

    def _refresh(self) -> None:
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        for b in backup_service.list_backups():
            try:
                size = os.path.getsize(b.backup_path)
            except OSError:
                size = 0
            self._tree.insert("", "end", iid=b.backup_id,
                              values=(b.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                                      self._fmt(size), b.backup_id))

    @staticmethod
    def _fmt(n: int) -> str:
        for u in ("B", "KB", "MB", "GB"):
            if abs(n) < 1024:
                return f"{n:.1f} {u}"
            n //= 1024
        return f"{n:.1f} TB"

    def _snapshot(self) -> None:
        path = self._path_var.get().strip()
        if not path or not os.path.exists(path):
            self._toast("Path does not exist.", kind="warning")
            return
        backup_service.snapshot_files([path], label="manual")
        self._toast(f"Snapshot created.", kind="success")
        self._refresh()

    def _restore(self) -> None:
        sel = self._tree.selection()
        if not sel:
            self._toast("Select a backup first.", kind="warning")
            return
        bid = sel[0]
        # find backup entry
        for b in backup_service.list_backups():
            if b.backup_id == bid:
                ok = backup_service.restore(b)
                self._toast(
                    "Restored." if ok else "Restore failed.",
                    kind="success" if ok else "error",
                )
                return

    def _delete(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        for bid in sel:
            for b in backup_service.list_backups():
                if b.backup_id == bid:
                    try:
                        os.remove(b.backup_path)
                    except OSError:
                        pass
                    break
        self._refresh()