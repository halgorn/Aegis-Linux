"""Reusable widgets. Each widget is a thin tkinter wrapper that knows
nothing about Aegis services — it just renders data it's given.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.ui.theme import current, font, fmt_pct, pct_color


# ── button ───────────────────────────────────────────────────────────────────

def button(parent, text: str, *, bg: str | None = None,
           fg: str | None = None, command=None, **kw):
    """Flat button that uses the current palette by default."""
    p = current()
    return tk.Button(
        parent, text=text, command=command,
        bg=bg or p.bg3, fg=fg or p.fg,
        font=font(10, bold=True), relief="flat",
        padx=12, pady=5, cursor="hand2",
        activebackground=bg or p.bg3,
        activeforeground=fg or p.fg, bd=0, **kw,
    )


def accent_button(parent, text: str, command=None, **kw):
    return button(parent, text, bg=current().blue, fg=current().bg,
                  command=command, **kw)


# ── treeview style ───────────────────────────────────────────────────────────

def apply_tree_style(style: ttk.Style | None = None) -> None:
    p = current()
    s = style or ttk.Style()
    s.theme_use("clam")
    s.configure("Treeview",
                background=p.bg3, foreground=p.fg,
                rowheight=28, fieldbackground=p.bg3,
                font=font(10), borderwidth=0)
    s.configure("Treeview.Heading",
                background=p.bg2, foreground=p.blue,
                font=font(10, bold=True), relief="flat")
    s.map("Treeview",
          background=[("selected", p.selection)],
          foreground=[("selected", p.fg)])
    s.configure("Vertical.TScrollbar",
                background=p.bg3, troughcolor=p.bg2,
                arrowcolor=p.fg2, borderwidth=0)
    s.configure("TProgressbar",
                troughcolor=p.bg2, background=p.blue, thickness=3)
    s.configure("TNotebook", background=p.bg2, borderwidth=0)
    s.configure("TNotebook.Tab",
                background=p.bg3, foreground=p.fg2,
                padding=[14, 6], font=font(10, bold=True))
    s.map("TNotebook.Tab",
          background=[("selected", p.bg)],
          foreground=[("selected", p.blue)])


# ── progress bar ─────────────────────────────────────────────────────────────

class ProgressBar(tk.Canvas):
    """Horizontal bar drawn with a single fill rect."""

    def __init__(self, parent, *, height: int = 14, bar_width: int = 0, **kw):
        super().__init__(parent, highlightthickness=0,
                         bg=current().bg, height=height, **kw)
        self._pb_h = height
        self._pb_w_hint = bar_width
        self.bind("<Configure>", lambda _e: self._render(0.0))

    def set(self, pct: float) -> None:
        self._render(max(0.0, min(1.0, pct)))

    def _render(self, pct: float) -> None:
        p = current()
        w = self.winfo_width() or self._pb_w_hint
        self.delete("all")
        self.create_rectangle(0, 0, w, self._pb_h, fill=p.bg3, outline=p.bg4)
        if pct > 0:
            self.create_rectangle(0, 1, int(w * pct), self._pb_h - 1,
                                  fill=pct_color(pct), outline="")


# ── card ─────────────────────────────────────────────────────────────────────

class Card(tk.Frame):
    """A bordered frame used everywhere in the UI."""

    def __init__(self, parent, *, title: str = "", accent: str | None = None):
        super().__init__(parent, bg=current().bg,
                         highlightthickness=1,
                         highlightbackground=current().border)
        if title:
            hdr = tk.Frame(self, bg=current().bg)
            hdr.pack(fill="x", padx=14, pady=(10, 0))
            tk.Label(hdr, text=title, font=font(11, bold=True),
                     fg=accent or current().blue,
                     bg=current().bg).pack(side="left")
        self.body = tk.Frame(self, bg=current().bg)
        self.body.pack(fill="both", expand=True, padx=14, pady=12)