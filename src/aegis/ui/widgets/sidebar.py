"""Sidebar navigation. Each nav item is a tuple ``(key, label, icon)``;
clicking emits a callback so the host can switch pages.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from aegis.ui.theme import current, font


@dataclass(slots=True, frozen=True)
class NavItem:
    key: str
    label: str
    icon: str = ""


class Sidebar(tk.Frame):
    """Vertical navigation strip on the left side of the main window."""

    def __init__(self, parent, items: list[NavItem],
                 on_select: Callable[[str], None],
                 *, width: int = 200) -> None:
        super().__init__(parent, bg=current().bg2, width=width)
        self._items = items
        self._on_select = on_select
        self._active: str | None = None
        self._buttons: dict[str, tk.Button] = {}
        self._build()

    def _build(self) -> None:
        p = current()
        # Brand
        brand = tk.Frame(self, bg=p.bg2, pady=14)
        brand.pack(fill="x")
        tk.Label(brand, text="AEGIS", font=("Helvetica", 18, "bold"),
                 fg=p.mauve, bg=p.bg2).pack()
        tk.Label(brand, text="Linux", font=font(9),
                 fg=p.fg2, bg=p.bg2).pack()
        tk.Frame(self, bg=p.border, height=1).pack(fill="x", pady=4)

        for item in self._items:
            row = tk.Frame(self, bg=p.bg2, padx=12, pady=2, cursor="hand2")
            row.pack(fill="x")
            lbl = tk.Label(row,
                           text=f"  {item.icon}  {item.label}" if item.icon
                                else f"  {item.label}",
                           font=font(10),
                           fg=p.fg, bg=p.bg2, anchor="w")
            lbl.pack(fill="x", pady=8)
            for w in (row, lbl):
                w.bind("<Button-1>", lambda _e, k=item.key: self.select(k))
                w.bind("<Enter>", lambda _e, k=item.key: self._hover(k))
                w.bind("<Leave>", lambda _e: self._unhover())
            self._buttons[item.key] = lbl   # type: ignore[assignment]

        # Spacer + footer
        tk.Frame(self, bg=p.bg2).pack(fill="both", expand=True)
        tk.Label(self, text=f"v0.1.0", font=font(8),
                 fg=p.fg2, bg=p.bg2).pack(side="bottom", pady=8)

    def select(self, key: str) -> None:
        if key not in self._buttons:
            return
        self._on_select(key)
        self._active = key
        self._refresh_active()

    def _refresh_active(self) -> None:
        p = current()
        for k, lbl in self._buttons.items():
            if k == self._active:
                lbl.configure(bg=p.bg4, fg=p.blue,
                              font=font(10, bold=True))
            else:
                lbl.configure(bg=p.bg2, fg=p.fg, font=font(10))

    def _hover(self, key: str) -> None:
        if key == self._active:
            return
        self._buttons[key].configure(bg=current().bg3)

    def _unhover(self) -> None:
        self._refresh_active()