"""SMART / NVMe / TRIM collectors."""

from __future__ import annotations

from dataclasses import dataclass

from aegis.core.logging import get_logger
from aegis.core.privileges import elevate
from aegis.core.process import run, which

_log = get_logger("collectors.smart")


@dataclass(slots=True, frozen=True)
class SmartReport:
    device: str
    passed: bool
    model: str
    serial: str
    temperature_c: float | None
    power_on_hours: int | None
    wear_pct: int | None
    reallocated: int | None
    raw_text: str


# ── disk inventory via lsblk ────────────────────────────────────────────────

def disk_devices() -> tuple[str, ...]:
    """Return ``/dev/sdX`` / ``/dev/nvmeXn1`` for every physical disk."""
    if which("lsblk") is None:
        return ()
    r = run(["lsblk", "-d", "-o", "NAME,TYPE", "--noheadings"], timeout=5)
    if not r.ok:
        return ()
    out: list[str] = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "disk":
            out.append("/dev/" + parts[0])
    return tuple(out)


# ── smartctl (elevated) ─────────────────────────────────────────────────────

def smart_report(device: str) -> SmartReport | None:
    """Run ``smartctl -H -A -i`` and parse a minimal report."""
    if which("smartctl") is None:
        return None
    r = elevate(["smartctl", "-H", "-A", "-i", device],
                reason=f"read SMART data from {device}", timeout=30)
    if not r.ok:
        _log.debug("smartctl %s failed: %s", device, r.stderr.strip())
        return None

    passed = False
    model = ""
    serial = ""
    temp: float | None = None
    poh: int | None = None
    wear: int | None = None
    reallocated: int | None = None

    for line in (r.stdout + "\n" + r.stderr).splitlines():
        low = line.lower()
        if "overall-health" in low or "result" in low:
            passed = "passed" in low or "ok" in low
        if low.startswith("device model:") or low.startswith("product:"):
            model = line.split(":", 1)[1].strip()
        if low.startswith("serial number:"):
            serial = line.split(":", 1)[1].strip()
        if "temperature" in low and "°c" in low:
            try:
                temp = float(line.rstrip("°c").split()[-1])
            except (ValueError, IndexError):
                pass
        if "power_on_hours" in low or "power on hours" in low:
            try:
                poh = int(line.split()[-1])
            except (ValueError, IndexError):
                pass
        if "wear_leveling" in low or "media_wearout" in low or "percent_lifetime" in low:
            try:
                wear = int(line.split()[-1])
            except (ValueError, IndexError):
                pass
        if "reallocated_sector" in low or "reallocated" in low:
            try:
                reallocated = int(line.split()[-1])
            except (ValueError, IndexError):
                pass

    return SmartReport(
        device=device, passed=passed, model=model, serial=serial,
        temperature_c=temp, power_on_hours=poh, wear_pct=wear,
        reallocated=reallocated, raw_text=r.stdout,
    )


def all_smart_reports() -> tuple[SmartReport, ...]:
    out: list[SmartReport] = []
    for dev in disk_devices():
        rep = smart_report(dev)
        if rep is not None:
            out.append(rep)
    return tuple(out)


# ── TRIM ────────────────────────────────────────────────────────────────────

def run_trim() -> str:
    """Run ``fstrim -av`` (all mounted filesystems)."""
    if which("fstrim") is None:
        return "fstrim not installed"
    r = elevate(["fstrim", "-av"], reason="run fstrim on all mounted SSDs")
    return r.stdout.strip() if r.ok else (r.stderr.strip() or "fstrim failed")