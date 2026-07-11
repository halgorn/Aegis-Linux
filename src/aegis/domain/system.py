"""Domain model — system metrics and resource snapshots.

Pure dataclasses, no I/O. Collectors read /proc, /sys and subprocess
output and produce these objects. Services consume them. UI renders
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True, frozen=True)
class MemorySample:
    """Snapshot of ``/proc/meminfo``."""

    total: int = 0
    free: int = 0
    available: int = 0
    buffers: int = 0
    cached: int = 0
    swap_total: int = 0
    swap_free: int = 0
    dirty: int = 0
    writeback: int = 0

    @property
    def used(self) -> int:
        return max(0, self.total - self.free - self.buffers - self.cached)

    @property
    def used_pct(self) -> float:
        return self.used / self.total if self.total else 0.0

    @property
    def swap_used(self) -> int:
        return max(0, self.swap_total - self.swap_free)

    @property
    def swap_used_pct(self) -> float:
        return self.swap_used / self.swap_total if self.swap_total else 0.0


@dataclass(slots=True, frozen=True)
class CpuSample:
    """Per-CPU instantaneous usage in percent (0.0 – 100.0 per core)."""

    per_core_pct: tuple[float, ...] = ()
    avg_pct: float = 0.0
    freq_mhz: float = 0.0
    temp_c: float | None = None
    governor: str = "—"
    cores: int = 0

    @property
    def load_label(self) -> str:
        return f"{self.avg_pct:.0f}%"


@dataclass(slots=True, frozen=True)
class DiskMount:
    """One line of ``df`` output."""

    device: str
    mount: str
    fstype: str
    size: int
    used: int
    avail: int

    @property
    def used_pct(self) -> float:
        return self.used / self.size if self.size else 0.0

    @property
    def is_full(self) -> bool:
        return self.used_pct >= 0.85


@dataclass(slots=True, frozen=True)
class DiskIoSample:
    """Cumulative ``/proc/diskstats`` counters."""

    read_bytes: int = 0
    write_bytes: int = 0
    read_iops: int = 0
    write_iops: int = 0


@dataclass(slots=True, frozen=True)
class NetSample:
    """Cumulative per-interface counters from ``/proc/net/dev``."""

    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    iface: str = ""


@dataclass(slots=True, frozen=True)
class GpuSample:
    """GPU telemetry (NVIDIA via nvidia-smi, AMD/Intel best-effort)."""

    vendor: str = "—"
    name: str = "—"
    util_pct: float | None = None
    vram_used: int | None = None
    vram_total: int | None = None
    temp_c: float | None = None
    power_w: float | None = None


@dataclass(slots=True, frozen=True)
class BatterySample:
    """Battery status from upower / sysfs."""

    present: bool = False
    capacity_pct: float | None = None
    state: str = "—"
    rate_w: float | None = None
    cycles: int | None = None
    health: str | None = None
    time_to_empty_min: float | None = None


@dataclass(slots=True, frozen=True)
class ProcessInfo:
    """One row of the process explorer."""

    pid: int
    ppid: int
    name: str
    cmdline: str
    user: str
    rss: int
    vsz: int
    cpu_pct: float
    nice: int
    threads: int
    state: str
    started: datetime | None = None


@dataclass(slots=True, frozen=True)
class SystemSnapshot:
    """A coherent point-in-time snapshot of the system."""

    ts: datetime
    cpu: CpuSample
    memory: MemorySample
    disks: tuple[DiskMount, ...]
    disk_io: DiskIoSample
    net: NetSample
    gpu: GpuSample
    battery: BatterySample
    load1: float = 0.0
    load5: float = 0.0
    load15: float = 0.0
    uptime_s: int = 0
    procs: tuple[ProcessInfo, ...] = field(default_factory=tuple)