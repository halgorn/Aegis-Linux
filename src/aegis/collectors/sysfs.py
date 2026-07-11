"""``/sys`` reader — CPU governor, frequency, I/O scheduler, hwmon temps."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aegis.core.logging import get_logger

_log = get_logger("collectors.sysfs")


# ── CPU governor / frequency ─────────────────────────────────────────────────

def cpu_governors() -> dict[str, str]:
    """``{cpu0: schedutil, cpu1: schedutil, …}``."""
    out: dict[str, str] = {}
    base = Path("/sys/devices/system/cpu")
    if not base.is_dir():
        return out
    for cpu in sorted(base.iterdir()):
        if not (cpu.name.startswith("cpu") and cpu.name[3:].isdigit()):
            continue
        f = cpu / "cpufreq" / "scaling_governor"
        try:
            out[cpu.name] = f.read_text().strip()
        except OSError:
            continue
    return out


def cpu_available_governors() -> list[str]:
    f = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors")
    if not f.is_file():
        return ["performance", "powersave", "schedutil", "ondemand", "conservative"]
    try:
        return f.read_text().strip().split()
    except OSError:
        return []


def cpu_max_freq_mhz() -> float:
    f = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
    if not f.is_file():
        return 0.0
    try:
        return int(f.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return 0.0


def cpu_cur_freq_mhz() -> float:
    f = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    if not f.is_file():
        return 0.0
    try:
        return int(f.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return 0.0


# ── I/O scheduler ────────────────────────────────────────────────────────────

def io_schedulers() -> dict[str, str]:
    out: dict[str, str] = {}
    base = Path("/sys/block")
    if not base.is_dir():
        return out
    for dev in base.iterdir():
        f = dev / "queue" / "scheduler"
        if not f.is_file():
            continue
        try:
            out[dev.name] = f.read_text().strip()
        except OSError:
            continue
    return out


# ── Temperatures (hwmon + thermal_zone) ──────────────────────────────────────

@dataclass(slots=True, frozen=True)
class TempReading:
    label: str
    celsius: float
    source: str         # hwmon | thermal_zone | sensors


def read_temperatures() -> list[TempReading]:
    """Return every temperature sensor we can find."""
    out: list[TempReading] = []
    base = Path("/sys/class/hwmon")
    if base.is_dir():
        for entry in base.iterdir():
            name_file = entry / "name"
            try:
                chip_name = name_file.read_text().strip() if name_file.is_file() else entry.name
            except OSError:
                chip_name = entry.name
            for f in entry.glob("temp*_input"):
                if not f.name.endswith("_input"):
                    continue
                try:
                    raw = int(f.read_text().strip())
                except (OSError, ValueError):
                    continue
                label_num = f.name[len("temp"):-len("_input")]
                label = f"{chip_name} temp{label_num}"
                out.append(TempReading(label=label, celsius=raw / 1000.0,
                                       source="hwmon"))

    # Fallback: /sys/class/thermal/thermal_zone*/temp
    tz = Path("/sys/class/thermal")
    if not out and tz.is_dir():
        for zone in tz.iterdir():
            f = zone / "temp"
            if not f.is_file():
                continue
            try:
                raw = int(f.read_text().strip())
            except (OSError, ValueError):
                continue
            out.append(TempReading(label=zone.name, celsius=raw / 1000.0,
                                   source="thermal_zone"))
    return out


def read_sensors_temperatures() -> list[TempReading]:
    """Optional: parse ``sensors`` (lm-sensors) output. Empty on failure."""
    from aegis.core.process import run, which
    if which("sensors") is None:
        return []
    r = run(["sensors"], timeout=5)
    if not r.ok:
        return []
    out: list[TempReading] = []
    for line in r.stdout.splitlines():
        if "°C" not in line:
            continue
        if ":" not in line:
            continue
        label, rest = line.split(":", 1)
        val_str = rest.split("(")[0].strip().replace("°C", "").replace("+", "")
        try:
            c = float(val_str)
        except ValueError:
            continue
        out.append(TempReading(label=label.strip(), celsius=c, source="sensors"))
    return out


# ── sysctl-style tunables ────────────────────────────────────────────────────

def read_sysctl(path: str, default: str = "0") -> int:
    """Read a sysctl value from ``/proc/sys/...`` safely."""
    f = Path("/proc/sys") / path
    try:
        return int(f.read_text().strip())
    except (OSError, ValueError):
        return int(default) if default.lstrip("-").isdigit() else 0


def write_sysctl(path: str, value: int | str) -> bool:
    """Write a sysctl value. Caller must hold privileges."""
    f = Path("/proc/sys") / path
    try:
        f.write_text(str(value))
        return True
    except OSError as exc:
        _log.warning("write_sysctl %s=%s failed: %s", path, value, exc)
        return False