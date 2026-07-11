"""Security collectors — SUID/SGID, world-writable, SSH keys, rootkit,
firewall rules, persistent systemd/cron changes, integrity."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run, which
from aegis.domain.health import Severity
from aegis.domain.security import PermissionIssue, SecurityFinding

_log = get_logger("collectors.security")

# Permission recommendations
_SSH_DIR_MODE       = 0o700
_SSH_PRIVATE_MODE    = 0o600
_SSH_PUBLIC_MODE     = 0o644


# ── permission scans ────────────────────────────────────────────────────────

def world_writable_files(root: str = os.path.expanduser("~"),
                         max_depth: int = 6,
                         limit: int = 200) -> tuple[str, ...]:
    """Return up to ``limit`` paths under ``root`` with o+w bit set."""
    out: list[str] = []
    base = Path(root)
    if not base.exists():
        return ()
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        depth = len(Path(dirpath).relative_to(base).parts)
        if depth >= max_depth:
            dirnames.clear()
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in list(dirnames) + filenames:
            fp = os.path.join(dirpath, name)
            if os.path.islink(fp):
                continue
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            if st.st_mode & 0o002:  # world-writable
                out.append(fp)
                if len(out) >= limit:
                    return tuple(out)
    return tuple(out)


def suid_sgid_files(root: str = "/usr",
                    skip: tuple[str, ...] = ("/proc", "/sys", "/snap"),
                    limit: int = 200) -> tuple[str, ...]:
    """Return SUID/SGID binaries under ``root`` (best-effort, slow)."""
    out: list[str] = []
    base = Path(root)
    if not base.exists():
        return ()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and not any(d.startswith(s) for s in skip)]
        for fname in filenames:
            fp = os.path.join(dirpath, fname)
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            if not os.path.isfile(fp):
                continue
            if st.st_mode & (0o4000 | 0o2000):  # SUID or SGID
                out.append(fp)
                if len(out) >= limit:
                    return tuple(out)
    return tuple(out)


def ssh_key_issues(ssh_dir: str | None = None) -> tuple[PermissionIssue, ...]:
    """Audit ``~/.ssh`` permissions. Returns one issue per wrong file."""
    ssh = Path(ssh_dir or os.path.expanduser("~/.ssh"))
    if not ssh.is_dir():
        return ()
    issues: list[PermissionIssue] = []
    try:
        mode = ssh.stat().st_mode & 0o777
        if mode != _SSH_DIR_MODE:
            issues.append(PermissionIssue(
                path=str(ssh),
                current_mode=mode,
                expected_mode=_SSH_DIR_MODE,
                reason=f"directory mode {oct(mode)} should be 700",
            ))
    except OSError:
        return tuple(issues)

    for entry in ssh.iterdir():
        try:
            st = entry.lstat()
        except OSError:
            continue
        if entry.is_dir():
            continue
        m = st.st_mode & 0o777
        if entry.name.endswith(".pub"):
            if m not in (_SSH_PUBLIC_MODE, 0o600, 0o400):
                issues.append(PermissionIssue(
                    path=str(entry),
                    current_mode=m,
                    expected_mode=_SSH_PUBLIC_MODE,
                    reason=f"public key mode {oct(m)} should be 644",
                ))
            continue
        if entry.name.startswith("known_hosts") or \
           entry.name.startswith("authorized_keys") or \
           entry.name.startswith("config"):
            continue
        if m not in (_SSH_PRIVATE_MODE, 0o400):
            issues.append(PermissionIssue(
                path=str(entry),
                current_mode=m,
                expected_mode=_SSH_PRIVATE_MODE,
                reason=f"private key mode {oct(m)} should be 600",
            ))
    return tuple(issues)


# ── rootkit hints ───────────────────────────────────────────────────────────

def rkhunter_summary() -> str:
    """Run ``rkhunter --check --skip-keypress --report-warnings-only``.

    Falls back to a friendly message if not installed. The actual
    scan requires root; we surface that in the output.
    """
    if which("rkhunter") is None:
        return "rkhunter not installed\nInstall: sudo apt install rkhunter"
    from aegis.core.privileges import elevate
    r = elevate(["rkhunter", "--check", "--skip-keypress",
                 "--report-warnings-only"],
                reason="run rkhunter rootkit scan")
    if not r.ok:
        return f"rkhunter failed (rc={r.returncode}): {r.stderr.strip()}"
    return (r.stdout + "\n" + r.stderr).strip() or "no warnings"


# ── systemd ─────────────────────────────────────────────────────────────────

def failed_services() -> tuple[tuple[str, str], ...]:
    """``((unit, state), …)`` for every failed systemd unit."""
    if which("systemctl") is None:
        return ()
    r = run(["systemctl", "--failed", "--no-legend", "--plain",
             "--no-pager"], timeout=10)
    if not r.ok:
        return ()
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        out.append((parts[0], " ".join(parts[1:4])))
    return tuple(out)


def running_services() -> tuple[str, ...]:
    if which("systemctl") is None:
        return ()
    r = run(["systemctl", "list-units", "--type=service", "--state=running",
             "--no-legend", "--no-pager"], timeout=10)
    if not r.ok:
        return ()
    return tuple(line.split()[0] for line in r.stdout.splitlines() if line.split())


# ── suspicious patterns ─────────────────────────────────────────────────────

def _walk_user_cron() -> tuple[SecurityFinding, ...]:
    """Look for cron jobs pointing at world-writable scripts."""
    out: list[SecurityFinding] = []
    cron_dir = Path("/var/spool/cron/crontabs")
    if not cron_dir.exists():
        return ()
    try:
        entries = list(cron_dir.iterdir())
    except OSError:
        return ()
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            text = entry.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "/tmp/" in line or "/dev/shm/" in line:
                out.append(SecurityFinding(
                    code="cron.tmp_exec",
                    title=f"Suspicious cron entry in {entry.name}:{i}",
                    detail=line,
                    severity=Severity.MEDIUM,
                    suggestion="Avoid running scripts from /tmp or /dev/shm",
                ))
    return tuple(out)


def _walk_systemd_persistence() -> tuple[SecurityFinding, ...]:
    """Find systemd unit files referencing suspicious paths."""
    out: list[SecurityFinding] = []
    paths = ("/etc/systemd/system", "/usr/lib/systemd/system",
             os.path.expanduser("~/.config/systemd/user"))
    for root in paths:
        base = Path(root)
        if not base.is_dir():
            continue
        for f in base.rglob("*.service"):
            try:
                text = f.read_text(errors="replace")
            except OSError:
                continue
            for marker in ("/tmp/", "/dev/shm/", "nc -e", "ncat -e"):
                if marker in text:
                    out.append(SecurityFinding(
                        code="systemd.suspicious",
                        title=f"Suspicious unit file: {f}",
                        detail=f"contains '{marker}'",
                        severity=Severity.HIGH,
                        suggestion="Inspect with `systemctl cat <unit>`",
                    ))
                    break
    return tuple(out)


def persistence_findings() -> tuple[SecurityFinding, ...]:
    """Aggregate cron + systemd suspicion checks."""
    return _walk_user_cron() + _walk_systemd_persistence()


# ── security score aggregator ────────────────────────────────────────────────

def ssh_config_audit(path: str = "/etc/ssh/sshd_config") -> tuple[SecurityFinding, ...]:
    if not os.path.isfile(path):
        return ()
    out: list[SecurityFinding] = []
    try:
        text = Path(path).read_text()
    except OSError:
        return ()
    if re.search(r"^\s*PermitRootLogin\s+yes", text, re.M):
        out.append(SecurityFinding(
            code="ssh.root_login",
            title="SSH: PermitRootLogin yes",
            detail="Root can log in via SSH.",
            severity=Severity.HIGH,
            suggestion="Set 'PermitRootLogin no' or 'prohibit-password'.",
        ))
    if re.search(r"^\s*PasswordAuthentication\s+yes", text, re.M):
        out.append(SecurityFinding(
            code="ssh.password_auth",
            title="SSH: PasswordAuthentication yes",
            detail="Passwords accepted; prefer keys.",
            severity=Severity.MEDIUM,
            suggestion="Set 'PasswordAuthentication no' if you use keys.",
        ))
    return tuple(out)


def selinux_status() -> str:
    if which("getenforce") is None:
        return "SELinux not installed"
    r = run(["getenforce"], timeout=3)
    return r.stdout.strip() if r.ok else "unknown"


def apparmor_status() -> str:
    if which("aa-status") is None:
        return "AppArmor not installed"
    r = run(["aa-status", "--brief"], timeout=5)
    if not r.ok:
        return "AppArmor inactive"
    line1 = r.stdout.splitlines()[0] if r.stdout else "—"
    return line1.strip()