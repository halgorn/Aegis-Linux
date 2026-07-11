"""Hardware / driver collectors — lshw, lspci, lsusb, DKMS, firmware."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run, which

_log = get_logger("collectors.drivers")


@dataclass(slots=True, frozen=True)
class HwDevice:
    category: str           # network / storage / display / …
    vendor: str
    product: str
    driver: str = ""
    bus: str = ""           # pci / usb
    id: str = ""
    in_use: bool = True


# ── lshw ────────────────────────────────────────────────────────────────────

def lshw_inventory() -> tuple[HwDevice, ...]:
    if which("lshw") is None:
        return ()
    r = run(["lshw", "-json", "-short"], timeout=30)
    if not r.ok:
        return ()
    # lshw -json -short emits one JSON object per line.
    out: list[HwDevice] = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        desc = obj.get("description", "")
        vendor = obj.get("vendor", "")
        product = obj.get("product", "")
        out.append(HwDevice(
            category=desc.lower().split()[0] if desc else "",
            vendor=vendor,
            product=product or desc,
        ))
    return tuple(out)


# ── lspci / lsusb ──────────────────────────────────────────────────────────

def lspci_devices() -> tuple[HwDevice, ...]:
    if which("lspci") is None:
        return ()
    r = run(["lspci", "-mm"], timeout=10)
    if not r.ok:
        return ()
    out: list[HwDevice] = []
    for line in r.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        parts = [p.strip('"') for p in line.split('"')]
        if len(parts) < 4:
            continue
        # ``00:00.0 "Host bridge" "Intel Corporation" "Device" -r02``
        # Normalise: split on whitespace first, then strip quotes.
        fields = line.split()
        if len(fields) < 4:
            continue
        out.append(HwDevice(
            category=fields[1].strip('"'),
            vendor="",
            product=line,
            bus="pci",
        ))
    return tuple(out)


def lsusb_devices() -> tuple[HwDevice, ...]:
    if which("lsusb") is None:
        return ()
    r = run(["lsusb"], timeout=5)
    if not r.ok:
        return ()
    out: list[HwDevice] = []
    for line in r.stdout.splitlines():
        # Bus 001 Device 002: ID 8087:0024 Intel Corp. …
        if "ID" not in line:
            continue
        try:
            right = line.split("ID", 1)[1].strip()
            vid_pid, _, name = right.partition(" ")
            out.append(HwDevice(
                category="usb",
                vendor=vid_pid.split(":")[0],
                product=name.strip(),
                bus="usb",
                id=vid_pid,
            ))
        except (ValueError, IndexError):
            continue
    return tuple(out)


# ── DKMS ────────────────────────────────────────────────────────────────────

def dkms_status() -> tuple[tuple[str, str, str], ...]:
    """Return ``((module, version, state), …)`` from ``dkms status``."""
    if which("dkms") is None:
        return ()
    r = run(["dkms", "status"], timeout=15)
    if not r.ok:
        return ()
    out: list[tuple[str, str, str]] = []
    for line in r.stdout.splitlines():
        # ``nvidia/535.171.04, 6.8.0-45-generic, x86_64: installed``
        head, _, state = line.rpartition(":")
        if not head:
            continue
        parts = [p.strip() for p in head.split(",")]
        if len(parts) < 2:
            continue
        out.append((parts[0], parts[1], state.strip()))
    return tuple(out)


# ── firmware ───────────────────────────────────────────────────────────────

def firmware_updates_available() -> int:
    """Return count of devices with firmware updates (via fwupdmgr)."""
    if which("fwupdmgr") is None:
        return -1
    r = run(["fwupdmgr", "get-updates", "--json"], timeout=30)
    if not r.ok:
        return 0
    try:
        obj = json.loads(r.stdout)
        devices = obj.get("Devices", [])
        return sum(1 for d in devices if d.get("Releases"))
    except ValueError:
        return 0


def cpu_microcode() -> str:
    """Return the loaded microcode version (best-effort)."""
    try:
        text = Path("/proc/cpuinfo").read_text()
    except OSError:
        return "—"
    for line in text.splitlines():
        if line.startswith("microcode"):
            return line.split(":", 1)[1].strip()
    return "—"


def loaded_modules_count() -> int:
    """Number of loaded kernel modules."""
    try:
        return sum(1 for line in Path("/proc/modules").read_text().splitlines()
                   if line.strip())
    except OSError:
        return 0


# ── GPU detection (lightweight, nvidia-smi still via collectors.gpu) ──────

def gpu_vendor_via_lshw() -> str:
    if which("lshw") is None:
        return ""
    r = run(["lshw", "-C", "display", "-json"], timeout=10)
    if not r.ok:
        return ""
    for line in r.stdout.splitlines():
        if not line.strip().startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        vendor = obj.get("vendor", "").lower()
        if "nvidia" in vendor:
            return "nvidia"
        if "amd" in vendor or "ati" in vendor:
            return "amd"
        if "intel" in vendor:
            return "intel"
    return ""