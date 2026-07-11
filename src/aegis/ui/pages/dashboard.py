"""Dashboard page — top-level system overview.

Cards: health score, CPU/MEM gauges, top issues, quick actions.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from aegis.domain.health import HealthReport, Severity
from aegis.domain.system import SystemSnapshot
from aegis.services.health_service import HealthService
from aegis.services.monitor_service import build_snapshot
from aegis.ui.theme import current, font, fmt_bytes, pct_color
from aegis.ui.widgets.charts import Gauge
from aegis.ui.widgets.common import Card, button
from aegis.ui.widgets.scrollable import ScrollableFrame


class DashboardPage(tk.Frame):
    """Single-page dashboard. Refreshed on demand + on focus."""

    def __init__(self, parent, *,
                 on_navigate: Callable[[str], None] | None = None) -> None:
        super().__init__(parent, bg=current().bg)
        self._nav = on_navigate or (lambda _k: None)
        self._report = HealthReport()
        self._snapshot = build_snapshot()
        self._build()

    def refresh(self) -> None:
        self._snapshot = build_snapshot()
        self._report = HealthService().run()
        self._render_cards()

    def _build(self) -> None:
        # Top row: 4 cards (score, cpu, mem, disk)
        top = tk.Frame(self, bg=current().bg)
        top.pack(fill="x", padx=14, pady=(14, 6))
        self._score_card = Card(top, title="Health score")
        self._score_card.pack(side="left", fill="both", expand=True, padx=4)
        self._cpu_card = Card(top, title="CPU")
        self._cpu_card.pack(side="left", fill="both", expand=True, padx=4)
        self._mem_card = Card(top, title="Memory")
        self._mem_card.pack(side="left", fill="both", expand=True, padx=4)
        self._disk_card = Card(top, title="Disk (/)")
        self._disk_card.pack(side="left", fill="both", expand=True, padx=4)

        # Bottom row: top issues + quick actions
        bot = tk.Frame(self, bg=current().bg)
        bot.pack(fill="both", expand=True, padx=14, pady=6)
        self._issues_card = Card(bot, title="Top issues")
        self._issues_card.pack(side="left", fill="both", expand=True, padx=4)
        self._actions_card = Card(bot, title="Quick actions")
        self._actions_card.pack(side="left", fill="both", expand=True, padx=4)

        self._render_cards()

    def _render_cards(self) -> None:
        p = current()
        r = self._report
        s = self._snapshot

        # Score
        for w in self._score_card.body.winfo_children(): w.destroy()
        c = current()
        color = c.green if r.score >= 80 else c.yellow if r.score >= 50 else c.red
        tk.Label(self._score_card.body, text=f"{r.score}",
                 font=("Helvetica", 36, "bold"),
                 fg=color, bg=current().bg).pack()
        tk.Label(self._score_card.body, text=f"grade {r.grade}  ·  "
                 f"{len(r.issues)} issue(s)",
                 fg=p.fg2, bg=p.bg, font=font(10)).pack()

        # CPU
        for w in self._cpu_card.body.winfo_children(): w.destroy()
        cpu_gauge = Gauge(self._cpu_card.body, size=120)
        cpu_gauge.set(s.cpu.avg_pct / 100.0)
        cpu_gauge.pack()
        tk.Label(self._cpu_card.body,
                 text=f"{s.cpu.cores} cores  ·  "
                      f"{s.cpu.freq_mhz:.0f} MHz" if s.cpu.freq_mhz else
                      f"{s.cpu.cores} cores",
                 fg=p.fg2, bg=p.bg, font=font(9)).pack()
        tk.Label(self._cpu_card.body, text=s.cpu.governor,
                 fg=p.cyan, bg=p.bg, font=font(9, bold=True)).pack()

        # Memory
        for w in self._mem_card.body.winfo_children(): w.destroy()
        mem_gauge = Gauge(self._mem_card.body, size=120)
        mem_gauge.set(s.memory.used_pct)
        mem_gauge.pack()
        used = fmt_bytes(s.memory.used)
        total = fmt_bytes(s.memory.total)
        tk.Label(self._mem_card.body, text=f"{used} / {total}",
                 fg=p.fg2, bg=p.bg, font=font(9)).pack()
        if s.memory.swap_total:
            tk.Label(self._mem_card.body,
                     text=f"swap {fmt_bytes(s.memory.swap_used)} / "
                          f"{fmt_bytes(s.memory.swap_total)}",
                     fg=p.mauve, bg=p.bg, font=font(9)).pack()

        # Disk
        for w in self._disk_card.body.winfo_children(): w.destroy()
        root = next((m for m in s.disks if m.mount == "/"),
                    s.disks[0] if s.disks else None)
        if root is None:
            tk.Label(self._disk_card.body, text="no mount",
                     fg=p.fg2, bg=p.bg).pack()
        else:
            dg = Gauge(self._disk_card.body, size=120)
            dg.set(root.used_pct)
            dg.pack()
            tk.Label(self._disk_card.body,
                     text=f"{fmt_bytes(root.used)} / {fmt_bytes(root.size)}",
                     fg=p.fg2, bg=p.bg, font=font(9)).pack()
            tk.Label(self._disk_card.body,
                     text=f"{root.fstype}  ·  {root.device.split('/')[-1]}",
                     fg=p.cyan, bg=p.bg, font=font(9)).pack()

        # Issues
        for w in self._issues_card.body.winfo_children(): w.destroy()
        worst = r.worst[:5]
        if not worst:
            tk.Label(self._issues_card.body, text="All good ✓",
                     fg=p.green, bg=p.bg,
                     font=font(11, bold=True)).pack(pady=8)
        else:
            for issue in worst:
                row = tk.Frame(self._issues_card.body, bg=p.bg)
                row.pack(fill="x", pady=2)
                colour = {
                    Severity.LOW: p.fg2, Severity.MEDIUM: p.yellow,
                    Severity.HIGH: p.red, Severity.CRITICAL: p.red,
                }.get(issue.severity, p.fg)
                tk.Label(row, text=f"● {issue.title}",
                         fg=colour, bg=p.bg,
                         font=font(10, bold=True),
                         anchor="w").pack(fill="x")
                tk.Label(row, text=f"  {issue.detail}",
                         fg=p.fg2, bg=p.bg,
                         font=font(9), anchor="w",
                         wraplength=320, justify="left").pack(fill="x")

        # Quick actions
        for w in self._actions_card.body.winfo_children(): w.destroy()
        actions = [
            ("Run Cleaner", "clean", p.green),
            ("Health Check", "health", p.blue),
            ("Monitor", "monitor", p.cyan),
            ("Network Diagnostics", "network", p.mauve),
            ("Driver Inventory", "drivers", p.yellow),
        ]
        for label, key, color in actions:
            button(self._actions_card.body, label, bg=color, fg=p.bg,
                   command=lambda k=key: self._nav(k)).pack(fill="x", pady=3)

        if not r.issues:
            button(self._actions_card.body, "Refresh", bg=p.bg3, fg=p.fg,
                   command=self.refresh).pack(fill="x", pady=(12, 0))


def make_dashboard(parent, on_navigate: Callable[[str], None] | None = None
                   ) -> DashboardPage:
    return DashboardPage(parent, on_navigate=on_navigate)