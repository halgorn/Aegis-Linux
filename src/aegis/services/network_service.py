"""Network interface + listening port discovery.

Reads ``/proc/net/*`` and ``/sys/class/net`` directly — no subprocess,
no root required for the read-only paths we use.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True, frozen=True)
class NetworkReport:
    interfaces: list[dict] = field(default_factory=list)
    listening: list[dict] = field(default_factory=list)


def scan() -> NetworkReport:
    return NetworkReport(interfaces=_interfaces(), listening=_listening())


def _interfaces() -> list[dict]:
    out: list[dict] = []
    base = Path("/sys/class/net")
    if not base.exists():
        return out
    for iface in sorted(base.iterdir()):
        try:
            state = (iface / "operstate").read_text().strip()
            speed_path = iface / "speed"
            speed = speed_path.read_text().strip() if speed_path.exists() else ""
            if speed in ("", "-1"):
                speed = ""
            else:
                try:
                    speed = f"{int(speed) // 1000} Gb/s"
                except ValueError:
                    speed = ""
            ipv4, ipv6 = _addrs(iface.name)
            out.append({
                "name": iface.name,
                "state": state,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "speed": speed,
            })
        except (OSError, PermissionError):
            continue
    return out


def _addrs(iface: str) -> tuple[list[str], list[str]]:
    """Best-effort via /proc/net/fib_trie; falls back to getaddrinfo on lo."""
    ipv4: list[str] = []
    ipv6: list[str] = []
    try:
        import psutil  # type: ignore
        addrs = psutil.net_if_addrs().get(iface, [])
        for a in addrs:
            fam = a.family
            if fam == socket.AF_INET:
                ipv4.append(a.address)
            elif fam == socket.AF_INET6:
                ipv6.append(a.address.split("%")[0])
    except Exception:
        if iface == "lo":
            ipv4.append("127.0.0.1")
            ipv6.append("::1")
    return ipv4, ipv6


def _listening() -> list[dict]:
    """``ss`` if available, else ``/proc/net/tcp{,6}`` parse."""
    out: list[dict] = []
    # Prefer psutil if available — it handles parsing for us.
    try:
        import psutil  # type: ignore
        for c in psutil.net_connections(kind="inet"):
            if c.status != psutil.CONN_LISTEN:
                continue
            proc = ""
            try:
                if c.pid:
                    proc = psutil.Process(c.pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc = ""
            out.append({
                "port": c.laddr.port,
                "proto": "tcp" if c.type == socket.SOCK_STREAM else "udp",
                "address": c.laddr.ip,
                "process": proc,
            })
        return out
    except Exception:
        pass
    # Fallback: parse /proc/net/tcp
    out = _parse_proc_net("/proc/net/tcp", "tcp")
    out += _parse_proc_net("/proc/net/tcp6", "tcp6")
    out += _parse_proc_net("/proc/net/udp", "udp")
    return out


def _parse_proc_net(path: str, proto: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[1]
        state = parts[3]
        if state != "0A":  # LISTEN
            continue
        try:
            ip_hex, port_hex = local.split(":")
            port = int(port_hex, 16)
            ip = _hex_to_ip(ip_hex)
        except ValueError:
            continue
        out.append({
            "port": port,
            "proto": proto,
            "address": ip,
            "process": "",
        })
    return out


def _hex_to_ip(h: str) -> str:
    """Reverse little-endian hex IP → dotted quad."""
    if len(h) != 8:
        return h
    try:
        b = bytes.fromhex(h)
        return ".".join(str(x) for x in reversed(b))
    except ValueError:
        return h