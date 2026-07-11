"""Tiny charts on a tk.Canvas — sparkline (line) + donut/ring gauge.
No matplotlib dependency."""

from __future__ import annotations

import tkinter as tk
from collections import deque
from collections.abc import Iterable

from aegis.ui.theme import current, pct_color


class Sparkline(tk.Canvas):
    """Minimal line chart with auto-scaling Y axis.

    ``append(value)`` adds a new sample; oldest is dropped when the
    buffer reaches ``maxlen``.
    """

    def __init__(self, parent, *,
                 maxlen: int = 120,
                 width: int = 480, height: int = 60,
                 color: str | None = None,
                 fill: bool = True):
        super().__init__(parent, width=width, height=height,
                         bg=current().bg2, highlightthickness=1,
                         highlightbackground=current().border)
        self._max = maxlen
        # NB: do NOT use self._w / self._h — tkinter uses these internally.
        self._w_hint = width
        self._h_hint = height
        self._color = color or current().blue
        self._data: deque[float] = deque(maxlen=maxlen)
        self._fill = fill
        self.bind("<Configure>", lambda _e: self._render())

    def append(self, v: float) -> None:
        self._data.append(v)
        self._render()

    def set_data(self, values: Iterable[float]) -> None:
        self._data.clear()
        for v in values:
            self._data.append(v)
        self._render()

    def _render(self) -> None:
        self.delete("all")
        if len(self._data) < 2:
            return
        w = self.winfo_width() or self._w_hint
        h = self.winfo_height() or self._h_hint
        values = list(self._data)
        lo, hi = min(values), max(values)
        rng = max(hi - lo, 1e-9)
        n = len(values)
        step = w / max(self._max - 1, 1)
        pts: list[float] = []
        for i, v in enumerate(values):
            x = w - (n - 1 - i) * step
            y = h - ((v - lo) / rng) * (h - 4) - 2
            pts.extend([x, y])
        if self._fill:
            poly = list(pts) + [w, h, pts[0], h]
            self.create_polygon(poly, fill=self._color, stipple="gray25",
                                outline="")
        self.create_line(pts, fill=self._color, width=2)
        self.create_text(w - 4, 4, anchor="ne",
                         text=f"{values[-1]:.0f}",
                         fill=self._color, font=("Helvetica", 9, "bold"))


class Gauge(tk.Canvas):
    """Half-donut gauge for percent values."""

    def __init__(self, parent, *, size: int = 80, thickness: int = 10):
        super().__init__(parent, width=size, height=size // 2 + thickness,
                         bg=current().bg, highlightthickness=0)
        self._gauge_size = size
        self._gauge_t = thickness

    def set(self, pct: float) -> None:
        self.delete("all")
        p = current()
        w = self._gauge_size
        h = self._gauge_size // 2 + self._gauge_t
        # background arc
        self.create_arc(self._gauge_t // 2, self._gauge_t // 2,
                        w - self._gauge_t // 2, w - self._gauge_t // 2,
                        start=0, extent=180,
                        style="arc", outline=p.bg3, width=self._gauge_t)
        # value arc
        deg = max(0.0, min(1.0, pct)) * 180.0
        if deg > 0:
            self.create_arc(self._gauge_t // 2, self._gauge_t // 2,
                            w - self._gauge_t // 2, w - self._gauge_t // 2,
                            start=0, extent=deg,
                            style="arc", outline=pct_color(pct),
                            width=self._gauge_t)
        # value text
        self.create_text(w // 2, h - 4, anchor="s",
                         text=f"{pct * 100:.0f}%",
                         fill=p.fg, font=("Helvetica", 10, "bold"))