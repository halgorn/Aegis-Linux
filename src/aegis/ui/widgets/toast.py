"""Toast — transient bottom-right notifications.

Non-blocking, auto-dismiss after ``timeout`` ms, queueable.
"""

from __future__ import annotations

import tkinter as tk
from collections import deque
from dataclasses import dataclass

from aegis.ui.theme import current, font


@dataclass(slots=True, frozen=True)
class _ToastSpec:
    text: str
    kind: str       # info / success / warning / error
    timeout_ms: int


class ToastHost:
    """Manages a stack of toasts in the bottom-right of ``root``."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._queue: deque[_ToastSpec] = deque()
        self._showing: tk.Toplevel | None = None

    def show(self, text: str, *,
             kind: str = "info",
             timeout_ms: int = 4000) -> None:
        self._queue.append(_ToastSpec(text, kind, timeout_ms))
        self._drain()

    def _drain(self) -> None:
        if self._showing is not None or not self._queue:
            return
        spec = self._queue.popleft()
        self._showing = self._build(spec)
        self._root.after(spec.timeout_ms, self._dismiss)

    def _build(self, spec: _ToastSpec) -> tk.Toplevel:
        p = current()
        bg_map = {
            "info": p.blue, "success": p.green,
            "warning": p.yellow, "error": p.red,
        }
        bg = bg_map.get(spec.kind, p.bg3)
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        f = tk.Frame(win, bg=bg, padx=14, pady=8)
        f.pack()
        tk.Label(f, text=spec.text, font=font(10, bold=True),
                 fg=p.bg, bg=bg).pack()
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        rw = self._root.winfo_width()
        rh = self._root.winfo_height()
        rx = self._root.winfo_rootx()
        ry = self._root.winfo_rooty()
        win.geometry(f"+{rx + rw - w - 16}+{ry + rh - h - 16}")
        return win

    def _dismiss(self) -> None:
        if self._showing is not None:
            try:
                self._showing.destroy()
            except tk.TclError:
                pass
            self._showing = None
        self._root.after(50, self._drain)