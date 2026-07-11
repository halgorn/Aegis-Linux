"""Domain model — packages and backups."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PkgManager(str, Enum):
    """Supported package managers."""

    APT = "apt"
    DNF = "dnf"
    PACMAN = "pacman"
    ZYPPER = "zypper"
    SNAP = "snap"
    FLATPAK = "flatpak"
    PIP = "pip"
    NPM = "npm"
    YARN = "yarn"
    PNPM = "pnpm"
    CARGO = "cargo"
    GO = "go"
    GEM = "gem"


@dataclass(slots=True, frozen=True)
class Package:
    """A single package known to a manager."""

    manager: PkgManager
    name: str
    version: str = "—"
    available: str = ""           # upgrade target, "" if up-to-date
    description: str = ""
    installed: bool = True
    size_bytes: int = 0


@dataclass(slots=True, frozen=True)
class PackageUpdate:
    """A pending upgrade."""

    pkg: Package
    is_security: bool = False
    source_url: str = ""


@dataclass(slots=True, frozen=True)
class RestorePoint:
    """A snapshot the user can roll back to."""

    id: str
    label: str
    created_at: datetime
    kind: str                       # config | btrfs | zfs | manual
    size_bytes: int = 0
    files: tuple[str, ...] = ()
    note: str = ""