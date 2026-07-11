"""Health page — runs HealthService and shows the report."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.domain.health import HealthIssue, Severity
from aegis.services.health_service import HealthService
from aegis.ui.theme import current, font
from aegis.ui.widgets.common import Card, button
from aegis.ui.widgets.scrollable import ScrollableFrame
from aegis.ui.widgets.toast import ToastHost


def _get_bridge(widget):
    """Walk up the Tk widget tree to find a registered MainThreadInvoker."""
    cur = widget
    while cur is not None:
        bridge = getattr(cur, "_aegis_bridge", None)
        if bridge is not None:
            return bridge
        cur = cur.master
    return None


_SEVERITY_COLOR = {
    Severity.INFO:    current().fg2,
    Severity.LOW:     current().fg2,
    Severity.MEDIUM:  current().yellow,
    Severity.HIGH:    current().red,
    Severity.CRITICAL: current().red,
}


class HealthPage(tk.Frame):
    def __init__(self, parent, *, toasts: ToastHost | None = None) -> None:
        super().__init__(parent, bg=current().bg)
        self._toasts = toasts
        self._issues: list[HealthIssue] = []
        self._runner = TaskRunner(max_workers=1)
        from aegis.core.concurrency import MainThreadInvoker
        # Reuse the application's bridge if registered globally.
        bridge = _get_bridge(parent)
        if bridge is not None:
            self._runner.set_main_invoker(bridge.invoke)
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=current().bg, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Health", font=("Helvetica", 18, "bold"),
                 fg=current().red, bg=current().bg).pack(side="left")
        self._score_lbl = tk.Label(hdr, text="—", font=("Helvetica", 16, "bold"),
                                   fg=current().fg, bg=current().bg)
        self._score_lbl.pack(side="left", padx=12)
        button(hdr, "Run scan", bg=current().red, fg=current().bg,
               command=self.run_scan).pack(side="right")

        self._body = ScrollableFrame(self)
        self._body.pack(fill="both", expand=True)

        self._status = tk.StringVar(value="Click 'Run scan' to evaluate.")
        tk.Label(self, textvariable=self._status, font=font(9),
                 fg=current().fg2, bg=current().bg2, anchor="w",
                 padx=14, pady=4).pack(fill="x")

    def run_scan(self) -> None:
        self._status.set("Scanning…")
        spec = TaskSpec(
            name="health_scan",
            fn=HealthService().run,
            on_done=lambda r: self._render(r),
        )
        self._runner.submit(spec)

    def _render(self, report) -> None:
        for w in self._body.inner.winfo_children():
            w.destroy()
        p = current()
        self._issues = list(report.issues)
        score_color = (p.green if report.score >= 80
                       else p.yellow if report.score >= 50
                       else p.red)
        self._score_lbl.config(text=f"{report.score}/100  (grade {report.grade})",
                               fg=score_color)
        self._status.set(f"Scan complete · {len(report.issues)} issue(s)")

        if not report.issues:
            tk.Label(self._body.inner, text="All good ✓",
                     fg=p.green, bg=p.bg, font=font(14, bold=True)).pack(pady=20)
            return

        for issue in report.issues:
            card = Card(self._body.inner,
                        title=issue.title,
                        accent=_SEVERITY_COLOR.get(issue.severity, p.fg))
            card.pack(fill="x", pady=6, padx=8)
            tk.Label(card.body, text=f"[{issue.severity.label.upper()}]  "
                     f"{issue.detail}",
                     fg=p.fg, bg=p.bg, font=font(10),
                     wraplength=600, justify="left").pack(anchor="w")
            if issue.suggestion:
                tk.Label(card.body, text=f"→ {issue.suggestion}",
                         fg=p.cyan, bg=p.bg, font=font(9),
                         wraplength=600, justify="left").pack(anchor="w")