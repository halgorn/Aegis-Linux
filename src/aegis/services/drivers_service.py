"""Kernel modules (drivers) inventory.

Reads ``/proc/modules`` — no root needed, no subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True, frozen=True)
class DriversReport:
    modules: list[dict] = field(default_factory=list)


def scan() -> DriversReport:
    return DriversReport(modules=_modules())


def _modules() -> list[dict]:
    p = Path("/proc/modules")
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        name, size, used, depends, state, addr = parts[:6]
        out.append({
            "name": name,
            "size": f"{int(size) // 1024} KB",
            "used_by": used if used != "-" else "",
            "state": state,
            "address": addr,
        })
    out.sort(key=lambda m: m["name"])
    return out