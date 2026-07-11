"""GPU collector — nvidia-smi (preferred) + DRM sysfs fallback."""

from __future__ import annotations

import re
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run, which
from aegis.domain.system import GpuSample

_log = get_logger("collectors.gpu")


def gpu_sample() -> GpuSample:
    """Best-effort GPU telemetry."""
    sample = _nvidia_smi()
    if sample is not None:
        return sample
    return _drm_sysfs() or GpuSample()


def _nvidia_smi() -> GpuSample | None:
    if which("nvidia-smi") is None:
        return None
    r = run(["nvidia-smi",
             "--query-gpu=name,temperature.gpu,memory.used,memory.total,"
             "utilization.gpu,power.draw",
             "--format=csv,noheader,nounits"], timeout=5)
    if not r.ok or not r.stdout.strip():
        return None
    parts = [p.strip() for p in r.stdout.strip().split(",")]
    if len(parts) < 5:
        return None
    try:
        name = parts[0]
        temp = float(parts[1])
        vram_used = int(parts[2]) * 1024 * 1024
        vram_total = int(parts[3]) * 1024 * 1024
        util = float(parts[4])
    except (ValueError, IndexError):
        return None
    power: float | None = None
    if len(parts) >= 6 and parts[5] not in ("", "[N/A]"):
        try:
            power = float(parts[5])
        except ValueError:
            pass
    return GpuSample(
        vendor="NVIDIA",
        name=name,
        util_pct=util,
        vram_used=vram_used,
        vram_total=vram_total,
        temp_c=temp,
        power_w=power,
    )


def _drm_sysfs() -> GpuSample | None:
    base = Path("/sys/class/drm")
    if not base.is_dir():
        return None
    for card in base.glob("card*"):
        device = card / "device"
        if not device.is_dir():
            continue
        uevent = device / "uevent"
        driver = ""
        if uevent.is_file():
            try:
                for line in uevent.read_text().splitlines():
                    if line.startswith("DRIVER="):
                        driver = line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass
        # Util / VRAM not exposed on AMD/Intel sysfs — leave None.
        return GpuSample(
            vendor=("AMD" if "amdgpu" in driver else
                    "Intel" if "i915" in driver else "—"),
            name=driver or "—",
        )
    return None


def gpu_processes() -> tuple[tuple[int, str, int], ...]:
    """Return ``(pid, name, used_mib)`` for processes using the GPU."""
    if which("nvidia-smi") is None:
        return ()
    r = run(["nvidia-smi",
             "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv,noheader,nounits"], timeout=5)
    if not r.ok:
        return ()
    out: list[tuple[int, str, int]] = []
    for line in r.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            out.append((int(parts[0]), parts[1], int(parts[2])))
        except ValueError:
            continue
    return tuple(out)