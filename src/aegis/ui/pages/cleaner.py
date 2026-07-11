"""Cleaner page — list of clean targets, calculate sizes, execute."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from aegis.core.concurrency import TaskRunner, TaskSpec
from aegis.domain.cleaner import CleanCategory, CleanPlan, CleanRecord, CleanTarget
from aegis.rules.cleaner_rules import by_category
from aegis.services.cleaner_service import CleanerService
from aegis.ui.theme import current, font, fmt_bytes
from aegis.ui.widgets.common import Card, button
from aegis.ui.widgets.confirm_dialog import confirm_clean
from aegis.ui.widgets.scrollable import ScrollableFrame
from aegis.ui.widgets.toast import ToastHost


def _get_bridge(widget):
    cur = widget
    while cur is not None:
        bridge = getattr(cur, "_aegis_bridge", None)
        if bridge is not None:
            return bridge
        cur = cur.master
    return None


@dataclass(slots=True)
class _Row:
    var: tk.BooleanVar
    size_lbl: tk.Label
    target: CleanTarget


class CleanerPage(tk.Frame):
    def __init__(self, parent, *,
                 toasts: ToastHost | None = None,
                 on_log: Callable[[str], None] | None = None) -> None:
        super().__init__(parent, bg=current().bg)
        self._toasts = toasts
        self._log = on_log or (lambda _s: None)
        self._rows: list[_Row] = []
        self._runner = TaskRunner(max_workers=2)
        # Use the app-wide main-thread bridge if available.
        bridge = _get_bridge(parent)
        if bridge is not None:
            self._runner.set_main_invoker(bridge.invoke)
        self._build()

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=current().bg, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Cleaner", font=("Helvetica", 18, "bold"),
                 fg=current().fg, bg=current().bg).pack(side="left")
        button(hdr, "Calculate sizes", bg=current().bg3, fg=current().fg,
               command=self._calc).pack(side="right", padx=(6, 0))
        button(hdr, "Clean selected", bg=current().red, fg=current().bg,
               command=self._clean).pack(side="right")

        # Body: cards per category
        body = ScrollableFrame(self)
        body.pack(fill="both", expand=True)

        for cat, targets in by_category().items():
            card = Card(body.inner, title=cat.value.replace("_", " ").title())
            card.pack(fill="x", pady=8, padx=8)
            for t in targets:
                self._add_row(card.body, t)

        # Footer / progress
        foot = tk.Frame(self, bg=current().bg2, pady=4)
        foot.pack(fill="x")
        self._progress = ttk.Progressbar(foot, mode="determinate")
        self._progress.pack(fill="x", padx=14, pady=2)
        self._status = tk.StringVar(value="Ready.")
        tk.Label(foot, textvariable=self._status, font=font(9),
                 fg=current().fg2, bg=current().bg2,
                 anchor="w", padx=14).pack(fill="x")

    # ── rows ──────────────────────────────────────────────────────────

    def _add_row(self, parent, target: CleanTarget) -> None:
        p = current()
        row = tk.Frame(parent, bg=p.bg3, padx=10, pady=6)
        row.pack(fill="x", pady=2)
        var = tk.BooleanVar(value=target.enabled_by_default)
        chk = tk.Checkbutton(row, variable=var, bg=p.bg3, fg=p.fg,
                             activebackground=p.bg3, selectcolor=p.bg4,
                             relief="flat")
        chk.pack(side="left")
        info = tk.Frame(row, bg=p.bg3)
        info.pack(side="left", fill="x", expand=True, padx=8)
        title_row = tk.Frame(info, bg=p.bg3)
        title_row.pack(fill="x")
        tk.Label(title_row, text=target.label, font=font(10, bold=True),
                 fg=p.fg, bg=p.bg3).pack(side="left")
        if target.needs_root:
            tk.Label(title_row, text=" [sudo]", font=font(9),
                     fg=p.red, bg=p.bg3).pack(side="left")
        tk.Label(info, text=target.description, font=font(9),
                 fg=p.fg2, bg=p.bg3, anchor="w",
                 wraplength=600, justify="left").pack(fill="x")
        size_lbl = tk.Label(row, text="—", font=font(10, bold=True),
                            fg=p.cyan, bg=p.bg3, width=12, anchor="e")
        size_lbl.pack(side="right")
        self._rows.append(_Row(var=var, size_lbl=size_lbl, target=target))

    # ── actions ───────────────────────────────────────────────────────

    def _selected(self) -> list[CleanTarget]:
        return [r.target for r in self._rows if r.var.get()]

    def _calc(self) -> None:
        selected = self._selected()
        if not selected:
            self._status.set("Select at least one item to calculate.")
            return
        self._status.set(f"Calculating sizes for {len(selected)} target(s)…")
        self._progress.configure(mode="indeterminate")
        self._progress.start(10)

        from aegis.services.cleaner_service import _estimate_target_size
        bridge = _get_bridge(self)

        def worker() -> None:
            sizes: list[tuple[_Row, int]] = []
            for r in self._rows:
                if r.target in selected and r.target.paths:
                    sz = _estimate_target_size(r.target)
                    if sz is not None:
                        object.__setattr__(r.target, "estimated_size", sz)
                        sizes.append((r, sz))
            return sizes

        def done(sizes: list[tuple[_Row, int]]) -> None:
            for r, sz in sizes:
                r.size_lbl.config(text=fmt_bytes(sz))
            self._calc_done()

        spec = TaskSpec(name="calc_sizes", fn=worker, on_done=done)
        self._runner.submit(spec)

    def _calc_done(self) -> None:
        self._progress.stop()
        self._status.set("Sizes calculated.")

    def _clean(self) -> None:
        selected = self._selected()
        if not selected:
            self._toast("Select at least one item.", kind="warning")
            return
        confirm = confirm_clean(
            self, selected,
            total_bytes=sum(t.estimated_size for t in selected),
        )
        if confirm is None or not confirm.proceed:
            return

        plan = CleanPlan(
            targets=selected,
            dry_run=not getattr(confirm, "_execute", True),
            create_backup=confirm.create_backup,
        )
        self._progress.configure(mode="determinate", value=0)
        self._status.set("Cleaning…")

        svc = CleanerService()
        bridge = _get_bridge(self)

        def worker() -> None:
            return svc.run(
                [t.id for t in plan.targets],
                dry_run=plan.dry_run,
                create_backup=plan.create_backup,
                on_record=lambda rec, b=bridge: b.invoke(self._on_record, rec),
            )

        spec = TaskSpec(
            name="clean",
            fn=worker,
            on_done=lambda result: self._done(result),
        )
        self._runner.submit(spec)

    def _on_record(self, rec: CleanRecord) -> None:
        if rec.ok:
            self._status.set(
                f"✓ {rec.label}  ·  {fmt_bytes(rec.bytes_freed)} freed"
            )
        else:
            self._status.set(f"✗ {rec.label}  ·  {rec.error}")
            self._toast(f"{rec.label} failed: {rec.error}", kind="error")

    def _done(self, result) -> None:
        self._progress.stop()
        msg = (f"Done. {result.bytes_freed / 1024**2:.0f} MB freed, "
               f"{result.files_removed} file(s).")
        self._status.set(msg)
        self._toast(msg, kind="success")
        self._log(result.to_text())

    def _toast(self, msg: str, *, kind: str = "info") -> None:
        if self._toasts is not None:
            self._toasts.show(msg, kind=kind)