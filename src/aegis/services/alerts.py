"""Threshold-based alerts raised from the monitor samples.

Runs alongside the live monitor; whenever a sample crosses one of
the thresholds, posts a toast (and a single-shot log entry). The
threshold values default to the ones from the original health
probes but can be lowered via Config if the user wants early
warning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from aegis.core.config import Config

_log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AlertThresholds:
    """Alert cuts at; 0 = disabled."""
    ram_pct: float = 0.85        # 85% RAM used
    disk_pct: float = 0.90       # 90% of root fs
    cpu_temp_c: float = 80.0     # 80 °C
    swap_pct: float = 0.50       # 50% swap

    @classmethod
    def from_config(cls, cfg: Config | None) -> "AlertThresholds":
        if cfg is None:
            return cls()
        # We keep all thresholds hard-coded for now — Config doesn't
        # expose overrides (yet). Future: add ``alert_*`` fields.
        return cls()


class AlertWatcher:
    """Track which alerts have fired this session so we don't spam."""

    def __init__(self, thresholds: AlertThresholds,
                 post: Callable[[str, str], None]) -> None:
        self._thr = thresholds
        self._post = post
        self._fired: set[str] = set()

    def reset(self) -> None:
        """Clear fired-set so alerts can fire again (e.g. after a fix)."""
        self._fired.clear()

    def check(self, sample) -> None:
        """Inspect one monitor sample and emit alerts that cross thresholds.

        ``sample`` is a ``MetricSample`` with mem_pct (0-1) /
        disk_used_pct (0-100) / swap_pct (0-1) / gpu_temp (°C, may be
        None on systems without GPU sensors). Anything missing is
        silently skipped — no alert, no crash.
        """
        # RAM
        if self._thr.ram_pct and getattr(sample, "mem_pct", None) is not None:
            pct = sample.mem_pct * 100
            if pct >= self._thr.ram_pct * 100 and "ram" not in self._fired:
                self._post(f"RAM at {pct:.0f}% - close some apps.", "warn")
                self._fired.add("ram")
        # Disk (root)
        if self._thr.disk_pct and getattr(sample, "disk_used_pct", None) is not None:
            pct = sample.disk_used_pct
            if pct >= self._thr.disk_pct * 100 and "disk" not in self._fired:
                self._post(
                    f"Disk at {pct:.0f}% - run Cleaner to reclaim space.", "warn")
                self._fired.add("disk")
        # GPU temp (proxy for "CPU too hot" — covers laptops + desktops)
        if self._thr.cpu_temp_c and getattr(sample, "gpu_temp", None) is not None:
            t = sample.gpu_temp
            if t >= self._thr.cpu_temp_c and "gpu_temp" not in self._fired:
                self._post(
                    f"GPU temperature {t:.0f}°C - check ventilation.", "warn")
                self._fired.add("gpu_temp")
        # Swap
        if self._thr.swap_pct and getattr(sample, "swap_pct", None) is not None:
            pct = sample.swap_pct * 100
            if pct >= self._thr.swap_pct * 100 and "swap" not in self._fired:
                self._post(f"Swap at {pct:.0f}% - consider adding RAM.", "warn")
                self._fired.add("swap")