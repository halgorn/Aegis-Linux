"""systemd startup services (user + system)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class StartupReport:
    items: list[dict] = field(default_factory=list)


def scan() -> StartupReport:
    items: list[dict] = []
    if not shutil.which("systemctl"):
        return StartupReport(items=[])
    for scope in ("user", "system"):
        try:
            r = subprocess.run(
                ["systemctl", "--user" if scope == "user" else "--system",
                 "list-unit-files", "--type=service", "--no-pager",
                 "--no-legend"],
                capture_output=True, text=True, timeout=15, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        for line in (r.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[0]
            state = parts[1]
            if state not in ("enabled", "enabled-runtime", "static"):
                continue
            if not name.endswith(".service"):
                continue
            desc = ""
            try:
                r2 = subprocess.run(
                    ["systemctl", "--user" if scope == "user" else "--system",
                     "show", name, "--property=Description"],
                    capture_output=True, text=True, timeout=4, check=False,
                )
                for ln in (r2.stdout or "").splitlines():
                    if ln.startswith("Description="):
                        desc = ln.split("=", 1)[1]
                        break
            except (subprocess.TimeoutExpired, OSError):
                pass
            items.append({
                "name": name.removesuffix(".service"),
                "scope": scope,
                "state": state,
                "description": desc,
            })
    items.sort(key=lambda x: (x["scope"], x["name"]))
    return StartupReport(items=items[:200])