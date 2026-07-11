"""Security page — list of findings from SecurityService."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.domain.security import SecurityFinding
from aegis.services.security_service import SecurityService
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


class SecurityPage(tk.Frame):
    def __init__(self, parent, *, toasts: ToastHost | None = None) -> None:
        super().__init__(parent, bg=current().bg)
        self._toasts = toasts
        self._findings: list[SecurityFinding] = []
        self._runner = TaskRunner(max_workers=1)
        bridge = _get_bridge(parent)
        if bridge is not None:
            self._runner.set_main_invoker(bridge.invoke)
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=current().bg, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Security", font=("Helvetica", 18, "bold"),
                 fg=current().red, bg=current().bg).pack(side="left")
        self._count_lbl = tk.Label(hdr, text="—", font=font(11, bold=True),
                                    fg=current().fg, bg=current().bg)
        self._count_lbl.pack(side="left", padx=12)
        button(hdr, "Scan", bg=current().red, fg=current().bg,
               command=self._scan).pack(side="right")

        self._body = ScrollableFrame(self)
        self._body.pack(fill="both", expand=True)

        self._status = tk.StringVar(value="Idle.")
        tk.Label(self, textvariable=self._status, font=font(9),
                 fg=current().fg2, bg=current().bg2,
                 anchor="w", padx=14, pady=4).pack(fill="x")

    def _scan(self) -> None:
        self._status.set("Scanning…")
        spec = TaskSpec(
            name="security_scan",
            fn=SecurityService().scan,
            on_done=lambda r: self._render(r),
        )
        self._runner.submit(spec)

    def _render(self, findings) -> None:
        p = current()
        for w in self._body.inner.winfo_children():
            w.destroy()
        self._findings = list(findings)
        self._count_lbl.config(
            text=f"{len(findings)} finding(s)",
            fg=p.green if not findings else p.yellow,
        )
        self._status.set(f"Done · {len(findings)} finding(s)")
        if not findings:
            tk.Label(self._body.inner, text="No security issues found ✓",
                     fg=p.green, bg=p.bg,
                     font=font(14, bold=True)).pack(pady=20)
            return
        for f in findings:
            card = Card(self._body.inner, title=f.title,
                        accent=p.red if f.severity.value >= 3 else p.yellow)
            card.pack(fill="x", pady=6, padx=8)
            tk.Label(card.body,
                     text=f"[{f.severity.label.upper()}]  {f.detail}",
                     fg=p.fg, bg=p.bg, font=font(10),
                     wraplength=600, justify="left").pack(anchor="w")
            if f.suggestion:
                tk.Label(card.body, text=f"→ {f.suggestion}",
                         fg=p.cyan, bg=p.bg, font=font(9),
                         wraplength=600, justify="left").pack(anchor="w")