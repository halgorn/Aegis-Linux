"""Network page — interfaces, ports, connections, DNS, ping."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.collectors import network as net_col
from aegis.ui.theme import current, font, fmt_bytes
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


class NetworkPage(tk.Frame):
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
        tk.Label(hdr, text="Network", font=("Helvetica", 18, "bold"),
                 fg=current().cyan, bg=current().bg).pack(side="left")
        button(hdr, "Refresh", bg=current().bg3, fg=current().fg,
               command=self._refresh_all).pack(side="right")

        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)

        # Interfaces
        self._ifaces_card = Card(body.inner, title="Interfaces")
        self._ifaces_card.pack(fill="x", padx=8, pady=6)

        # Listening ports
        self._ports_card = Card(body.inner, title="Listening ports")
        self._ports_card.pack(fill="both", expand=True, padx=8, pady=6)
        self._ports_tree = ttk.Treeview(self._ports_card.body,
                                         columns=("proto", "local",
                                                  "state", "process"),
                                         show="headings", height=8)
        for col, label, w in (("proto", "Proto", 70),
                              ("local", "Local", 220),
                              ("state", "State", 90),
                              ("process", "Process", 380)):
            self._ports_tree.heading(col, text=label)
            self._ports_tree.column(col, width=w, minwidth=60)
        vsb = ttk.Scrollbar(self._ports_card.body, orient="vertical",
                             command=self._ports_tree.yview)
        self._ports_tree.configure(yscrollcommand=vsb.set)
        self._ports_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Connectivity
        self._conn_card = Card(body.inner, title="Connectivity")
        self._conn_card.pack(fill="x", padx=8, pady=6)
        ping_bar = tk.Frame(self._conn_card.body, bg=current().bg)
        ping_bar.pack(anchor="w")
        tk.Label(ping_bar, text="Ping 8.8.8.8:",
                 fg=current().fg, bg=current().bg,
                 font=font(10)).pack(side="left")
        button(ping_bar, "Run", bg=current().cyan, fg=current().bg,
               command=self._ping).pack(side="left", padx=6)
        self._ping_lbl = tk.Label(ping_bar, text="—", fg=current().green,
                                    bg=current().bg, font=font(10, bold=True))
        self._ping_lbl.pack(side="left", padx=6)

        info_bar = tk.Frame(self._conn_card.body, bg=current().bg)
        info_bar.pack(fill="x", pady=4)
        self._gw_lbl = tk.Label(info_bar, text="Gateway: —",
                                 fg=current().fg, bg=current().bg,
                                 font=font(10))
        self._gw_lbl.pack(side="left", padx=(0, 12))
        self._dns_lbl = tk.Label(info_bar, text="DNS: —",
                                  fg=current().fg, bg=current().bg,
                                  font=font(10))
        self._dns_lbl.pack(side="left", padx=(0, 12))
        self._fw_lbl = tk.Label(info_bar, text="Firewall: —",
                                 fg=current().fg, bg=current().bg,
                                 font=font(10))
        self._fw_lbl.pack(side="left")

        self._refresh_all()

    def _refresh_all(self) -> None:
        self._runner.submit(TaskSpec(
            name="net_info",
            fn=lambda: (net_col.interfaces(), net_col.gateway(),
                        net_col.dns_servers(), net_col.firewall_active(),
                        net_col.listening_ports()),
            on_done=lambda r: self._render_info(*r),
        ))

    def _render_info(self, ifaces, gw, dns, fw, ports) -> None:
        for w in self._ifaces_card.body.winfo_children():
            w.destroy()
        p = current()
        for iface in ifaces:
            row = tk.Frame(self._ifaces_card.body, bg=p.bg)
            row.pack(fill="x", pady=2)
            state_color = p.green if iface.state == "up" else p.fg2
            tk.Label(row, text=iface.name, font=font(10, bold=True),
                     fg=p.fg, bg=p.bg, width=10, anchor="w").pack(side="left")
            tk.Label(row, text=iface.state, fg=state_color, bg=p.bg,
                     font=font(10)).pack(side="left", padx=6)
            tk.Label(row, text=f"rx {fmt_bytes(iface.rx_bytes)} "
                               f"tx {fmt_bytes(iface.tx_bytes)}",
                     fg=p.fg2, bg=p.bg, font=font(9)).pack(side="left",
                                                          padx=12)
        self._gw_lbl.config(text=f"Gateway: {gw or '—'}")
        self._dns_lbl.config(text=f"DNS: {', '.join(dns) if dns else '—'}")
        self._fw_lbl.config(
            text=f"Firewall: {'active' if fw else 'inactive' if fw is False else 'unknown'}",
            fg=p.green if fw else (p.red if fw is False else p.fg2),
        )
        for iid in self._ports_tree.get_children():
            self._ports_tree.delete(iid)
        for port in ports:
            self._ports_tree.insert(
                "", "end",
                values=(port.proto, port.local, port.state, port.process),
            )

    def _ping(self) -> None:
        spec = TaskSpec(
            name="ping",
            fn=lambda: net_col.ping("8.8.8.8", count=3, timeout=3),
            on_done=lambda r: self._ping_lbl.config(
                text=f"avg {r[0]:.0f} ms  ·  loss {r[1]:.0f}%"),
        )
        self._runner.submit(spec)