"""Startup collectors — systemd user services, autostart .desktop,
cron jobs, snap/flatpak autostart, boot time blame."""

from __future__ import annotations

import os
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run, which
from aegis.domain.security import StartupEntry

_log = get_logger("collectors.startup")


# ── autostart .desktop files ────────────────────────────────────────────────

_AUTOSTART_DIRS = (
    os.path.expanduser("~/.config/autostart"),
    "/etc/xdg/autostart",
    "/usr/share/autostart",
)


def autostart_desktop_entries() -> tuple[StartupEntry, ...]:
    out: list[StartupEntry] = []
    for d in _AUTOSTART_DIRS:
        base = Path(d)
        if not base.is_dir():
            continue
        for f in sorted(base.glob("*.desktop")):
            try:
                text = f.read_text(errors="replace")
            except OSError:
                continue
            entry: dict[str, str] = {}
            for line in text.splitlines():
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                entry[k.strip()] = v.strip()
            name = entry.get("Name", f.name)
            cmd = entry.get("Exec", "")
            hidden = entry.get("Hidden", "").lower() == "true"
            no_autostart = entry.get("X-GNOME-Autostart-enabled", "").lower() == "false"
            enabled = not (hidden or no_autostart)
            try:
                relpath = f.relative_to(Path.home()).as_posix()
            except ValueError:
                relpath = str(f)
            out.append(StartupEntry(
                id=f"autostart:{f}",
                name=name,
                source="autostart",
                enabled=enabled,
                command=cmd,
                file=relpath,
            ))
    return tuple(out)


# ── systemd user units ──────────────────────────────────────────────────────

def systemd_user_enabled() -> tuple[StartupEntry, ...]:
    if which("systemctl") is None:
        return ()
    r = run(["systemctl", "--user", "list-unit-files", "--state=enabled",
             "--no-legend", "--no-pager"], timeout=10)
    if not r.ok:
        return ()
    out: list[StartupEntry] = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        unit, state = parts[0], parts[1]
        out.append(StartupEntry(
            id=f"systemd-user:{unit}",
            name=unit,
            source="systemd-user",
            enabled=(state == "enabled"),
            file=unit,
        ))
    return tuple(out)


def systemd_system_enabled() -> tuple[StartupEntry, ...]:
    if which("systemctl") is None:
        return ()
    r = run(["systemctl", "list-unit-files", "--state=enabled",
             "--no-legend", "--no-pager"], timeout=15)
    if not r.ok:
        return ()
    out: list[StartupEntry] = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        unit, state = parts[0], parts[1]
        out.append(StartupEntry(
            id=f"systemd-system:{unit}",
            name=unit,
            source="systemd",
            enabled=(state == "enabled"),
            file=unit,
        ))
    return tuple(out)


# ── cron ────────────────────────────────────────────────────────────────────

def cron_jobs() -> tuple[StartupEntry, ...]:
    r = run(["crontab", "-l"], timeout=5)
    if not r.ok:
        return ()
    out: list[StartupEntry] = []
    for i, line in enumerate(r.stdout.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(StartupEntry(
            id=f"cron:{i}",
            name=f"line {i}",
            source="cron",
            enabled=True,
            command=line,
            file="user crontab",
        ))
    return tuple(out)


def toggle_autostart(file_path: str, enable: bool) -> str | None:
    """Flip Hidden/X-GNOME-Autostart-enabled in a .desktop file."""
    p = Path(file_path)
    if not p.is_file():
        return f"file not found: {file_path}"
    try:
        text = p.read_text()
    except OSError as exc:
        return str(exc)
    lines = [l for l in text.splitlines()
             if not l.startswith("Hidden=") and
             not l.startswith("X-GNOME-Autostart-enabled=")]
    if not enable:
        # Insert right after the [Desktop Entry] header
        idx = next((i for i, l in enumerate(lines)
                    if l.startswith("[Desktop")), 0)
        lines.insert(idx + 1, "X-GNOME-Autostart-enabled=false")
        lines.insert(idx + 1, "Hidden=true")
    try:
        p.write_text("\n".join(lines) + "\n")
    except OSError as exc:
        return str(exc)
    return None


def delete_autostart(file_path: str) -> str | None:
    try:
        os.remove(file_path)
    except OSError as exc:
        return str(exc)
    return None


# ── boot analysis ──────────────────────────────────────────────────────────

def boot_summary() -> str:
    if which("systemd-analyze") is None:
        return "systemd-analyze not available"
    r = run(["systemd-analyze"], timeout=10)
    return r.stdout.strip().split("\n")[0] if r.ok else "—"


def boot_blame(top: int = 25) -> tuple[tuple[str, str], ...]:
    if which("systemd-analyze") is None:
        return ()
    r = run(["systemd-analyze", "blame", "--no-pager"], timeout=30)
    if not r.ok:
        return ()
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines()[:top]:
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            out.append(parts)
    return tuple(out)


# ── installer helpers ──────────────────────────────────────────────────────

def install_cron_job(line: str) -> tuple[bool, str]:
    """Append ``line`` to the user crontab. Returns (ok, error_message)."""
    r = run(["crontab", "-l"], timeout=5)
    existing = r.stdout if r.ok else ""
    if line in existing:
        return False, "Already installed"
    new = existing.rstrip() + "\n" + line + "\n"
    proc = run(["crontab", "-"], timeout=5, input=new)
    if proc.ok:
        return True, ""
    return False, proc.stderr.strip()