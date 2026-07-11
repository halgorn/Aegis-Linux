"""Monitor service — periodic snapshots with a rolling history."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from aegis.collectors import disks as disks_col
from aegis.collectors import gpu as gpu_col
from aegis.collectors import network as net_col
from aegis.collectors import procfs as proc_col
from aegis.domain.system import SystemSnapshot

_log = None  # late-bound


def _log():
    from aegis.core.logging import get_logger
    return get_logger("services.monitor")


@dataclass(slots=True, frozen=True)
class MetricSample:
    ts: datetime
    cpu_pct: float
    mem_pct: float
    swap_pct: float
    rx_kbps: float
    tx_kbps: float
    disk_used_pct: float
    gpu_pct: float | None
    gpu_temp: float | None


class MonitorService:
    """Periodic sampler with bounded ring buffer.

    The sampler runs in its own thread. Callbacks fire on the
    sampler thread — consumers must marshal to the UI themselves
    (typically via :func:`aegis.core.events.bus`).
    """

    def __init__(self,
                 refresh_hz: float = 1.0,
                 history_seconds: int = 600,
                 on_sample: Callable[[MetricSample], None] | None = None,
                 ) -> None:
        self._refresh = max(0.2, refresh_hz)
        self._history: deque[MetricSample] = deque(
            maxlen=max(60, int(refresh_hz * history_seconds))
        )
        self._on_sample = on_sample
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_net = net_col.interfaces()
        self._last_ts: datetime | None = None

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="aegis-monitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ── sampling ─────────────────────────────────────────────────────

    def sample_once(self) -> MetricSample:
        return self._take_sample()

    def history(self) -> tuple[MetricSample, ...]:
        return tuple(self._history)

    # ── internal ─────────────────────────────────────────────────────

    def _run(self) -> None:
        period = 1.0 / self._refresh
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                sample = self._take_sample()
            except Exception:  # noqa: BLE001
                _log().exception("sample failed")
            else:
                self._history.append(sample)
                if self._on_sample is not None:
                    try:
                        self._on_sample(sample)
                    except Exception:  # noqa: BLE001
                        _log().exception("on_sample callback raised")
            elapsed = time.monotonic() - t0
            self._stop.wait(max(0.0, period - elapsed))

    def _take_sample(self) -> MetricSample:
        from aegis.collectors.procfs import read_cpu_sample

        cpu = read_cpu_sample()
        mem = proc_col.read_meminfo()
        mounts = disks_col.read_mounts()
        root_used_pct = next(
            (m.used_pct for m in mounts if m.mount == "/"),
            0.0,
        )
        net_now = {i.name: i for i in net_col.interfaces()}
        rx_kbps = tx_kbps = 0.0
        now = datetime.now(timezone.utc)
        if self._last_ts is not None:
            dt = max((now - self._last_ts).total_seconds(), 0.001)
            for name, iface in net_now.items():
                prev = self._last_net.get(name)
                if prev is None:
                    continue
                rx_kbps += max(0.0, (iface.rx_bytes - prev.rx_bytes) / 1024.0 / dt)
                tx_kbps += max(0.0, (iface.tx_bytes - prev.tx_bytes) / 1024.0 / dt)
        self._last_net = net_now
        self._last_ts = now
        gpu = gpu_col.gpu_sample()
        return MetricSample(
            ts=now,
            cpu_pct=cpu.avg_pct,
            mem_pct=mem.used_pct,
            swap_pct=mem.swap_used_pct,
            rx_kbps=rx_kbps,
            tx_kbps=tx_kbps,
            disk_used_pct=root_used_pct,
            gpu_pct=gpu.util_pct,
            gpu_temp=gpu.temp_c,
        )


def build_snapshot() -> SystemSnapshot:
    """One-off point-in-time snapshot used by the dashboard / CLI."""
    l1, l5, l15 = proc_col.read_loadavg()
    diskstats = disks_col.read_diskstats()
    primary = next(iter(diskstats), None)
    disk_io = diskstats.get(primary) if primary else None
    if disk_io is None:
        from aegis.domain.system import DiskIoSample
        disk_io = DiskIoSample()
    from aegis.domain.system import NetSample
    net = NetSample()
    return SystemSnapshot(
        ts=datetime.now(timezone.utc),
        cpu=proc_col.read_cpu_sample(),
        memory=proc_col.read_meminfo(),
        disks=disks_col.read_mounts(),
        disk_io=disk_io,
        net=net,
        gpu=gpu_col.gpu_sample(),
        battery=proc_col.read_battery(),
        load1=l1,
        load5=l5,
        load15=l15,
        uptime_s=proc_col.read_uptime_s(),
        procs=proc_col.list_processes(top=22),
    )