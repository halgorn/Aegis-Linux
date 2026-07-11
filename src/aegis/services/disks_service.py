"""Disk filesystem usage + SMART availability check."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class DisksReport:
    filesystems: list[dict] = field(default_factory=list)
    smart: list[dict] = field(default_factory=list)


def scan() -> DisksReport:
    return DisksReport(filesystems=_filesystems(), smart=_smart())


def _filesystems() -> list[dict]:
    out: list[dict] = []
    try:
        import psutil  # type: ignore
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            out.append({
                "mount": part.mountpoint,
                "device": part.device,
                "fstype": part.fstype,
                "used": u.used,
                "total": u.total,
                "percent": u.percent,
            })
    except Exception:
        # Fallback: just / + /home
        for mp in ("/", str(__import__("pathlib").Path.home())):
            try:
                u = shutil.disk_usage(mp)
                out.append({
                    "mount": mp,
                    "device": mp,
                    "fstype": "?",
                    "used": u.used,
                    "total": u.total,
                    "percent": int(u.used * 100 / max(u.total, 1)),
                })
            except OSError:
                pass
    return out


def _smart() -> list[dict]:
    """Best-effort. Returns empty list when ``smartctl`` is not installed
    or no permission to query devices. The page UI shows a friendly
    message in that case."""
    import shutil as _sh
    import subprocess
    if not _sh.which("smartctl"):
        return []
    try:
        r = subprocess.run(
            ["smartctl", "--scan"], capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    out: list[dict] = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append({"device": line.split()[0] if line else "?"})
    return out[:8]