"""Filesystem integrity — broken symlinks, orphan .desktop entries,
package-integrity check (dpkg -V), unused dependencies."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run, which

_log = get_logger("collectors.integrity")


# ── broken symlinks ─────────────────────────────────────────────────────────

def broken_symlinks(root: str | None = None,
                    skip: tuple[str, ...] = ("proc", "sys", "dev", "run",
                                              "snap", "boot", "tmp"),
                    limit: int = 500,
                    ) -> tuple[str, ...]:
    """Return paths of broken symlinks under ``root`` (default: $HOME)."""
    from aegis.collectors.filesystem import find_broken_symlinks
    base = root or os.path.expanduser("~")
    return find_broken_symlinks(base, skip_names=frozenset(skip))[:limit]


# ── orphan .desktop ─────────────────────────────────────────────────────────

_DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
)


def orphan_desktop_entries() -> tuple[tuple[str, str], ...]:
    """``((file, exec_cmd), …)`` for .desktop entries pointing to
    commands that don't exist."""
    out: list[tuple[str, str]] = []
    for d in _DESKTOP_DIRS:
        base = Path(d)
        if not base.is_dir():
            continue
        for f in base.iterdir():
            if not f.name.endswith(".desktop"):
                continue
            try:
                text = f.read_text(errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if not line.startswith("Exec="):
                    continue
                cmd_raw = line.split("=", 1)[1].strip()
                cmd = cmd_raw.split()[0].split("%")[0].strip() if cmd_raw else ""
                if not cmd:
                    break
                if cmd.startswith("/"):
                    ok = os.path.isfile(cmd)
                else:
                    ok = shutil.which(cmd) is not None
                if not ok:
                    out.append((str(f), cmd))
                break
    return tuple(out)


# ── unused dependencies (apt autoremove hint) ────────────────────────────────

def apt_unused_packages() -> tuple[str, ...]:
    """Run ``apt-get -s autoremove`` and parse the simulation output."""
    if which("apt-get") is None:
        return ()
    r = run(["apt-get", "-s", "autoremove", "--purge"], timeout=30)
    if not r.ok:
        return ()
    out: list[str] = []
    capture = False
    for line in r.stdout.splitlines():
        if line.startswith("The following packages will be REMOVED:"):
            capture = True
            continue
        if capture:
            if not line.startswith(" "):
                if out:
                    break
                continue
            out.extend(line.split())
    return tuple(out)


# ── dpkg verify (modified files) ────────────────────────────────────────────


def dpkg_modified_files(limit: int = 50) -> tuple[tuple[str, str], ...]:
    """Return ``((path, status), …)`` for files modified since install.

    ``status`` is the dpkg-V code (5 = md5 mismatch, etc.).
    """
    if which("dpkg") is None:
        return ()
    r = run(["dpkg", "--verify"], timeout=60, allow_shell=False)
    if not r.ok:
        return ()
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines():
        # ``??5?????? c /etc/somefile``
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        status, path = parts[0], parts[2]
        if status == "??5??????":  # md5 mismatch (interesting)
            out.append((path, status))
            if len(out) >= limit:
                break
    return tuple(out)


# ── old kernels (Debian/Ubuntu) ──────────────────────────────────────────────

def old_kernels(current: str | None = None) -> tuple[str, ...]:
    """List installed ``linux-image-*`` packages that aren't the running kernel."""
    if which("dpkg") is None:
        return ()
    if current is None:
        import platform
        current = platform.uname().release
    r = run(["dpkg", "--list"], timeout=15)
    if not r.ok:
        return ()
    out: list[str] = []
    for line in r.stdout.splitlines():
        if not line.startswith("ii"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pkg = parts[1]
        if not pkg.startswith("linux-image-"):
            continue
        if "linux-image-generic" in pkg:
            continue
        if current in pkg:
            continue
        out.append(pkg)
    return tuple(out)