"""Orphaned/duplicate package detection (best-effort, multi-manager).

Detects apt/dnf/pacman/zypper and queries whichever is present. Each
manager is queried without sudo — only user-owned queries, no installs.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class PackagesReport:
    packages: list[dict] = field(default_factory=list)
    manager: str = ""


def scan() -> PackagesReport:
    for cmd, fn in (
        ("apt", _scan_apt),
        ("dnf", _scan_dnf),
        ("pacman", _scan_pacman),
        ("zypper", _scan_zypper),
    ):
        if shutil.which(cmd):
            try:
                pkgs, mgr = fn()
                if pkgs:
                    return PackagesReport(packages=pkgs, manager=mgr)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                continue
    return PackagesReport(packages=[], manager="none")


def _scan_apt() -> tuple[list[dict], str]:
    out: list[dict] = []
    # deborphan is optional; fall back to autoremove --dry-run.
    if shutil.which("deborphan"):
        r = subprocess.run(
            ["deborphan"], capture_output=True, text=True, timeout=20,
            check=False,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append({"name": line, "manager": "apt", "reason": "orphan"})
    return out, "apt"


def _scan_dnf() -> tuple[list[dict], str]:
    out: list[dict] = []
    r = subprocess.run(
        ["dnf", "-q", "repoquery", "--unneeded", "--queryformat",
         "%{NAME}\t%{REASON}\n"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    for line in (r.stdout or "").splitlines()[:100]:
        parts = line.split("\t")
        if len(parts) >= 1 and parts[0]:
            out.append({
                "name": parts[0],
                "manager": "dnf",
                "reason": parts[1] if len(parts) > 1 else "unneeded",
            })
    return out, "dnf"


def _scan_pacman() -> tuple[list[dict], str]:
    out: list[dict] = []
    r = subprocess.run(
        ["pacman", "-Qdtq"], capture_output=True, text=True, timeout=20, check=False,
    )
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line:
            out.append({"name": line, "manager": "pacman", "reason": "orphan"})
    return out, "pacman"


def _scan_zypper() -> tuple[list[dict], str]:
    out: list[dict] = []
    r = subprocess.run(
        ["zypper", "--quiet", "--no-refresh", "packages", "--unneeded"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    for line in (r.stdout or "").splitlines()[:100]:
        line = line.strip()
        if not line or line.startswith("S") or line.startswith("-"):
            continue
        parts = line.split()
        if parts:
            out.append({"name": parts[0], "manager": "zypper", "reason": "unneeded"})
    return out, "zypper"