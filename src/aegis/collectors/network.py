"""Network collectors — interfaces, ports, connections, DNS, firewall,
firewall info, /etc/hosts."""

from __future__ import annotations

import os
import re
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run, which
from aegis.domain.security import Connection, InterfaceInfo, Port

_log = get_logger("collectors.network")


# ── interfaces ───────────────────────────────────────────────────────────────

def interfaces() -> tuple[InterfaceInfo, ...]:
    """Inspect every interface via ``/sys/class/net`` + ``ip addr``."""
    base = Path("/sys/class/net")
    if not base.is_dir():
        return ()
    out: list[InterfaceInfo] = []
    for entry in base.iterdir():
        name = entry.name
        try:
            state = (entry / "operstate").read_text().strip()
        except OSError:
            state = "unknown"
        try:
            mac = (entry / "address").read_text().strip()
        except OSError:
            mac = ""
        is_wifi = (entry / "wireless").exists() or (entry / "phy80211").exists()
        rx = _read_int(entry / "statistics" / "rx_bytes")
        tx = _read_int(entry / "statistics" / "tx_bytes")
        speed = _read_int(entry / "speed")
        out.append(InterfaceInfo(
            name=name, state=state, mac=mac,
            rx_bytes=rx, tx_bytes=tx,
            speed_mbps=speed if speed else None,
            is_wifi=is_wifi,
        ))
    return tuple(out)


def ipv4_addresses() -> dict[str, tuple[str, ...]]:
    """``{iface: (addr/prefix, …)}`` from ``ip -o addr``."""
    r = run(["ip", "-o", "-4", "addr"], timeout=5)
    out: dict[str, tuple[str, ...]] = {}
    if not r.ok:
        return out
    for line in r.stdout.splitlines():
        parts = line.split()
        # ``2: eth0    inet 192.168.1.10/24 brd …``
        if len(parts) < 4:
            continue
        iface = parts[1]
        addr = parts[3]
        out.setdefault(iface, []).append(addr)
    return {k: tuple(v) for k, v in out.items()}


def gateway() -> str | None:
    r = run(["ip", "route", "show", "default"], timeout=5)
    if not r.ok:
        return None
    for line in r.stdout.splitlines():
        m = re.search(r"via\s+(\S+)", line)
        if m:
            return m.group(1)
    return None


def dns_servers() -> tuple[str, ...]:
    """Read ``/etc/resolv.conf`` (no systemd-resolve needed)."""
    try:
        text = Path("/etc/resolv.conf").read_text()
    except OSError:
        return ()
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("nameserver"):
            parts = line.split()
            if len(parts) >= 2:
                out.append(parts[1])
    return tuple(out)


def wifi_ssid(iface: str = "wlan0") -> str:
    """Return the SSID ``iface`` is connected to, or ``''`` on failure."""
    if which("iwgetid") is None:
        return ""
    r = run(["iwgetid", "-r", iface], timeout=3)
    return r.stdout.strip() if r.ok else ""


# ── ports / connections ─────────────────────────────────────────────────────

def listening_ports() -> tuple[Port, ...]:
    r = run(["ss", "-tulnp"], timeout=5)
    if not r.ok:
        return ()
    out: list[Port] = []
    for i, line in enumerate(r.stdout.splitlines()):
        if i == 0:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, state = parts[0], parts[1]
        local = parts[4]
        process = parts[6] if len(parts) > 6 else "—"
        pid = _extract_pid(process)
        out.append(Port(proto=proto, local=local, state=state,
                        process=process.split(",")[0] if process else "—",
                        pid=pid))
    return tuple(out)


def active_connections() -> tuple[Connection, ...]:
    r = run(["ss", "-tp", "--no-header"], timeout=5)
    if not r.ok:
        return ()
    out: list[Connection] = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        out.append(Connection(
            proto="tcp",  # ss -tp is tcp-only by default
            state=parts[0],
            local=parts[3],
            remote=parts[4],
            process=parts[5] if len(parts) > 5 else "—",
        ))
    return tuple(out)


# ── firewall ────────────────────────────────────────────────────────────────

def ufw_status() -> str:
    if which("ufw") is None:
        return "ufw not installed"
    r = run(["ufw", "status", "verbose"], timeout=5)
    return r.stdout.strip() if r.ok else "ufw inactive"


def firewall_active() -> bool | None:
    """Return ``True`` if any firewall backend is detected, ``None`` if
    we cannot determine."""
    for cmd in ("ufw", "firewalld", "nft", "iptables"):
        if which(cmd) is None:
            continue
        if cmd == "ufw":
            if "Status: active" in ufw_status():
                return True
        if cmd == "nft":
            r = run(["nft", "list", "ruleset"], timeout=5)
            if r.ok and r.stdout.strip():
                return True
        if cmd == "iptables":
            r = run(["iptables", "-S"], timeout=5)
            if r.ok and len(r.stdout.splitlines()) > 3:
                return True
    return None


def flush_dns() -> bool:
    """Best-effort cache flush. Tries resolvectl then systemd-resolve."""
    for cmd in (["resolvectl", "flush-caches"],
                ["systemd-resolve", "--flush-caches"]):
        if which(cmd[0]) is not None:
            r = run(cmd, timeout=5)
            if r.ok:
                return True
    return False


# ── /etc/hosts ──────────────────────────────────────────────────────────────

def read_hosts() -> str:
    try:
        return Path("/etc/hosts").read_text()
    except OSError:
        return ""


def write_hosts(content: str) -> bool:
    """Atomic write: temp file + pkexec mv. Caller must confirm with user."""
    from aegis.core.privileges import elevate
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix=".aegis-hosts-", text=True)
    try:
        with os.fdopen(fd, "w") as fp:
            fp.write(content)
        r = elevate(["cp", tmp, "/etc/hosts"], reason="write /etc/hosts")
        return r.ok
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ── helpers ─────────────────────────────────────────────────────────────────

def _read_int(path: Path) -> int:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return 0


_PID_RE = re.compile(r"pid=(\d+)")


def _extract_pid(process_field: str) -> int | None:
    m = _PID_RE.search(process_field)
    return int(m.group(1)) if m else None


def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return ""


def ping(host: str, count: int = 3, timeout: int = 5) -> tuple[float, float]:
    """Return ``(avg_ms, packet_loss_pct)`` from ``ping -c``."""
    if which("ping") is None:
        return 0.0, 100.0
    r = run(["ping", "-c", str(count), "-W", str(timeout), host], timeout=timeout + 5)
    if not r.ok:
        return 0.0, 100.0
    avg = 0.0
    loss = 100.0
    for line in r.stdout.splitlines():
        if "packet loss" in line:
            m = re.search(r"(\d+(?:\.\d+)?)% packet loss", line)
            if m:
                loss = float(m.group(1))
        if "rtt min/avg/max" in line or "round-trip" in line:
            m = re.search(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)/", line)
            if m:
                avg = float(m.group(2))
    return avg, loss