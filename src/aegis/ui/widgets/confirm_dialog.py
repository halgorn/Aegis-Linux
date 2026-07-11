"""Confirmation dialog — shows what will happen before destructive ops.

Used by the cleaner before any non-dry-run execution. Returns
``True`` only if the user clicks the explicit "Yes, clean" button.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from dataclasses import dataclass
from tkinter import ttk

from aegis.domain.cleaner import CleanTarget
from aegis.ui.theme import current, font


@dataclass(slots=True, frozen=True)
class ConfirmResult:
    proceed: bool
    create_backup: bool


def confirm_clean(parent: tk.Misc,
                  targets: Iterable[CleanTarget],
                  total_bytes: int,
                  *,
                  dry_run_default: bool = True,
                  backup_default: bool = True,
                  ) -> ConfirmResult | None:
    """Modal dialog. Returns ``None`` if cancelled, else the choice."""
    p = current()
    win = tk.Toplevel(parent)
    win.title("Confirm cleanup")
    win.configure(bg=p.bg)
    win.transient(parent)
    win.grab_set()
    win.geometry("520x460")

    tk.Label(win, text="Confirm cleanup", font=font(14, bold=True),
             fg=p.red, bg=p.bg).pack(pady=(14, 4))

    tk.Label(win, text="The following will be cleaned:",
             fg=p.fg, bg=p.bg, font=font(10)).pack()

    body = tk.Frame(win, bg=p.bg2, padx=12, pady=8)
    body.pack(fill="both", expand=True, padx=14, pady=8)

    txt = tk.Text(body, bg=p.bg3, fg=p.fg, font=("Courier", 9),
                  relief="flat", height=12, padx=8, pady=8)
    txt.pack(fill="both", expand=True)
    for t in targets:
        line = f"  • {t.label:<32}  ~{_fmt(total_bytes // max(1, len(list(targets))))}\n"
        txt.insert("end", line)
    txt.config(state="disabled")

    opts = tk.Frame(win, bg=p.bg)
    opts.pack(fill="x", padx=14)
    backup_var = tk.BooleanVar(value=backup_default)
    dry_var = tk.BooleanVar(value=dry_run_default)
    if backup_default:
        tk.Checkbutton(opts, text="Create backup before cleanup",
                       variable=backup_var, bg=p.bg, fg=p.fg,
                       activebackground=p.bg, selectcolor=p.bg4,
                       font=font(10)).pack(anchor="w")
    tk.Checkbutton(opts, text="Dry run (preview only, don't delete)",
                   variable=dry_var, bg=p.bg, fg=p.fg,
                   activebackground=p.bg, selectcolor=p.bg4,
                   font=font(10)).pack(anchor="w")

    result: list[ConfirmResult] = []

    def ok() -> None:
        result.append(ConfirmResult(
            proceed=True,
            create_backup=backup_var.get(),
        ))
        win.destroy()

    def cancel() -> None:
        result.append(ConfirmResult(proceed=False, create_backup=False))
        win.destroy()

    bar = tk.Frame(win, bg=p.bg)
    bar.pack(fill="x", pady=10)
    tk.Button(bar, text="Cancel", command=cancel, bg=p.bg3, fg=p.fg,
              font=font(10, bold=True), relief="flat",
              padx=14, pady=6, cursor="hand2", bd=0).pack(side="right", padx=6)
    tk.Button(bar, text="Yes, clean", command=ok, bg=p.red, fg=p.bg,
              font=font(10, bold=True), relief="flat",
              padx=14, pady=6, cursor="hand2", bd=0).pack(side="right")

    parent.wait_window(win)
    if not result:
        return None
    return result[0]


def _fmt(n: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {u}"
        n //= 1024
    return f"{n:.1f} PB"