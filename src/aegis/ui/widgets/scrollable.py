"""Scrollable frame — a Canvas + Frame with mouse-wheel binding **per
instance** (no global ``bind_all`` leaks like in the legacy code)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.ui.theme import current


class ScrollableFrame(tk.Frame):
    """Vertically-scrollable container.

    Usage::

        body = ScrollableFrame(parent)
        body.pack(fill="both", expand=True)
        tk.Label(body.inner, text="...").pack()
    """

    def __init__(self, parent, *, bg: str | None = None, **kw):
        super().__init__(parent, bg=bg or current().bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg or current().bg,
                                 highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.inner = tk.Frame(self.canvas, bg=bg or current().bg)

        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._win, width=e.width),
        )
        # Per-canvas mouse wheel — no bind_all leaks.
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

    def _bind_wheel(self, _event) -> None:
        self.canvas.bind_all("<Button-4>", self._on_wheel)
        self.canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self, _event) -> None:
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event) -> str | None:
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        return "break"