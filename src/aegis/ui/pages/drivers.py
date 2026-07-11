"""Drivers page — hardware inventory + firmware + DKMS status."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.collectors import drivers as drv_col
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


class DriversPage(tk.Frame):
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
        tk.Label(hdr, text="Drivers", font=("Helvetica", 18, "bold"),
                 fg=current().yellow, bg=current().bg).pack(side="left")
        button(hdr, "Refresh", bg=current().bg3, fg=current().fg,
               command=self._refresh).pack(side="right")

        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)

        # Summary cards
        summary = tk.Frame(body.inner, bg=current().bg)
        summary.pack(fill="x", padx=8, pady=6)
        for i in range(4):
            summary.columnconfigure(i, weight=1)
        self._micro_lbl = self._summary_card(summary, "Microcode", 0)
        self._modules_lbl = self._summary_card(summary, "Kernel modules", 1)
        self._fw_lbl = self._summary_card(summary, "Firmware updates", 2)
        self._dkms_lbl = self._summary_card(summary, "DKMS modules", 3)

        # PCI / USB trees
        for title, attr in (("PCI devices", "_pci"),
                             ("USB devices", "_usb"),
                             ("DKMS status", "_dkms")):
            card = Card(body.inner, title=title)
            card.pack(fill="x", padx=8, pady=6)
            tree = ttk.Treeview(card.body, columns=("info",), show="headings")
            tree.heading("info", text="Detail")
            tree.column("info", width=900, minwidth=200)
            setattr(self, attr, tree)
            tree.pack(fill="both", expand=True)

        self._refresh()

    def _summary_card(self, parent, title, col):
        c = Card(parent, title=title)
        c.grid(row=0, column=col, sticky="nsew", padx=4)
        lbl = tk.Label(c.body, text="—", font=("Helvetica", 14, "bold"),
                       fg=current().fg, bg=current().bg)
        lbl.pack()
        return lbl

    def _refresh(self) -> None:
        self._runner.submit(TaskSpec(
            name="drivers",
            fn=lambda: (
                drv_col.cpu_microcode(),
                drv_col.loaded_modules_count(),
                drv_col.firmware_updates_available(),
                drv_col.dkms_status(),
                drv_col.lspci_devices(),
                drv_col.lsusb_devices(),
            ),
            on_done=lambda r: self._render(*r),
        ))

    def _render(self, micro, mods, fw, dkms, pci, usb) -> None:
        p = current()
        self._micro_lbl.config(text=micro or "—",
                               fg=p.green if micro and micro != "—" else p.fg2)
        self._modules_lbl.config(text=str(mods), fg=p.fg)
        if fw < 0:
            self._fw_lbl.config(text="n/a", fg=p.fg2)
        else:
            color = p.green if fw == 0 else p.yellow
            self._fw_lbl.config(text=str(fw), fg=color)
        self._dkms_lbl.config(text=str(len(dkms)),
                              fg=p.green if dkms else p.fg2)

        for tree, rows in ((self._pci, pci),
                           (self._usb, usb)):
            for iid in tree.get_children():
                tree.delete(iid)
            for r in rows[:60]:
                tree.insert("", "end", values=(r.product,))

        for iid in self._dkms.get_children():
            self._dkms.delete(iid)
        for mod, ver, st in dkms:
            self._dkms.insert("", "end",
                              values=(f"{mod}  {ver}  ·  {st}",))