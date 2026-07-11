"""Domain model — security findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from aegis.domain.health import Severity


@dataclass(slots=True, frozen=True)
class Port:
    """An open listening port."""

    proto: str           # tcp / udp
    local: str           # 0.0.0.0:22 or [::]:22
    state: str           # LISTEN, …
    process: str = "—"
    pid: int | None = None


@dataclass(slots=True, frozen=True)
class Connection:
    """An active (non-listening) connection."""

    proto: str
    state: str
    local: str
    remote: str
    process: str = "—"


@dataclass(slots=True, frozen=True)
class PermissionIssue:
    """A file / directory with wrong permissions."""

    path: str
    current_mode: int
    expected_mode: int
    reason: str


@dataclass(slots=True, frozen=True)
class StartupEntry:
    """Something that runs at login / boot."""

    id: str
    name: str
    source: str                  # systemd / cron / autostart / snap / flatpak
    enabled: bool
    command: str = ""
    file: str = ""
    boot_impact_ms: int = 0


@dataclass(slots=True, frozen=True)
class SecurityFinding:
    """One item reported by the security scanner."""

    code: str
    title: str
    detail: str
    severity: Severity
    suggestion: str = ""
    data: dict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class InterfaceInfo:
    """Network interface summary."""

    name: str
    state: str                   # up / down / unknown
    mac: str = ""
    ipv4: tuple[str, ...] = ()
    ipv6: tuple[str, ...] = ()
    rx_bytes: int = 0
    tx_bytes: int = 0
    speed_mbps: int | None = None
    is_wifi: bool = False
    ssid: str = ""