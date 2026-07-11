"""``/proc`` reader — memory, CPU, processes, load average, uptime.

Everything is best-effort: if a file is unreadable we return a
zeroed sample instead of raising. The monitor service expects to
be called frequently; raising on transient errors would kill the
loop.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.domain.system import (
    BatterySample,
    CpuSample,
    MemorySample,
    ProcessInfo,
)

_log = get_logger("collectors.procfs")
_PROC = Path("/proc")


# ── /proc/meminfo ─────────────────────────────────────────────────────────────

def read_meminfo() -> MemorySample:
    """Parse ``/proc/meminfo`` into a :class:`MemorySample`."""
    info: dict[str, int] = {}
    try:
        text = (_PROC / "meminfo").read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _log.debug("meminfo unreadable: %s", exc)
        return MemorySample()

    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        parts = v.strip().split()
        try:
            info[k.strip()] = int(parts[0]) * 1024 if len(parts) >= 2 else int(parts[0])
        except ValueError:
            continue

    return MemorySample(
        total=info.get("MemTotal", 0),
        free=info.get("MemFree", 0),
        available=info.get("MemAvailable", info.get("MemFree", 0)),
        buffers=info.get("Buffers", 0),
        cached=info.get("Cached", 0) + info.get("SReclaimable", 0),
        swap_total=info.get("SwapTotal", 0),
        swap_free=info.get("SwapFree", 0),
        dirty=info.get("Dirty", 0),
        writeback=info.get("Writeback", 0),
    )


# ── /proc/loadavg ─────────────────────────────────────────────────────────────

def read_loadavg() -> tuple[float, float, float]:
    """Return ``(load1, load5, load15)``."""
    try:
        parts = (_PROC / "loadavg").read_text().split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except (OSError, ValueError, IndexError):
        return 0.0, 0.0, 0.0


# ── /proc/uptime ──────────────────────────────────────────────────────────────

def read_uptime_s() -> int:
    try:
        return int(float((_PROC / "uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return 0


# ── /proc/stat (CPU) ─────────────────────────────────────────────────────────

@dataclass(slots=True)
class _CpuTimes:
    user: int = 0
    nice: int = 0
    system: int = 0
    idle: int = 0
    iowait: int = 0
    irq: int = 0
    softirq: int = 0
    steal: int = 0
    total: int = 0


_LAST_CPU: dict[int, _CpuTimes] = {}


def read_cpu_sample() -> CpuSample:
    """Compute per-core usage since the last call."""
    try:
        text = (_PROC / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return CpuSample()

    cores: list[float] = []
    governors: list[str] = []
    freq = 0.0
    for line in text.splitlines():
        if not line.startswith("cpu"):
            break
        parts = line.split()
        if not parts[0].startswith("cpu"):
            continue
        try:
            nums = [int(p) for p in parts[1:8]]
        except ValueError:
            continue
        cur = _CpuTimes(
            user=nums[0], nice=nums[1], system=nums[2], idle=nums[3],
            iowait=nums[4], irq=nums[5], softirq=nums[6],
            total=sum(nums),
        )
        prev = _LAST_CPU.get(len(cores))
        if prev is not None and cur.total > prev.total:
            busy = (cur.total - cur.idle - cur.iowait) - (prev.total - prev.idle - prev.iowait)
            denom = cur.total - prev.total
            cores.append(max(0.0, min(100.0, busy * 100.0 / denom)))
        _LAST_CPU[len(cores)] = cur

    # Per-CPU governor + frequency are read elsewhere; here we just
    # provide a placeholder (avg of first core).
    return CpuSample(
        per_core_pct=tuple(cores),
        avg_pct=sum(cores) / len(cores) if cores else 0.0,
        cores=len(cores),
        freq_mhz=freq,
        governor=", ".join(sorted(set(governors))) if governors else "—",
    )


# ── /proc/<pid>/{stat,status,cmdline} ────────────────────────────────────────

def _read_proc_status(pid: str) -> dict[str, str]:
    try:
        text = (_PROC / pid / "status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _read_proc_cmdline(pid: str) -> str:
    try:
        raw = (_PROC / pid / "cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def _read_proc_stat(pid: str) -> tuple[str, int, int, int, int, int]:
    """Return ``(comm, ppid, nice, rss_pages, threads, state_code)``."""
    try:
        raw = (_PROC / pid / "stat").read_text()
    except OSError:
        return "?", 0, 0, 0, 1, "?"
    # `comm` is parenthesised and may contain spaces — split on last ')'.
    rp = raw.rfind(")")
    if rp < 0:
        return "?", 0, 0, 0, 1, "?"
    head, tail = raw[:rp], raw[rp + 1 :]
    parts = (head.split()[1] if head else "?").split()  # drop pid prefix
    tail_parts = tail.split()
    try:
        state = tail_parts[0]
        ppid = int(tail_parts[2])
        nice = int(tail_parts[16])
        threads = int(tail_parts[17])
        rss_pages = int(tail_parts[21])
    except (IndexError, ValueError):
        return "?", 0, 0, 0, 1, "?"
    return parts[0] if parts else "?", ppid, nice, rss_pages, threads, state


def _proc_started(pid: str) -> datetime | None:
    try:
        st = os.stat(_PROC / pid)
    except OSError:
        return None
    return datetime.fromtimestamp(st.st_ctime)


def list_processes(top: int = 22) -> tuple[ProcessInfo, ...]:
    """Top-``top`` processes by RSS. Cheap single-pass scan."""
    out: list[ProcessInfo] = []
    try:
        pids = [p for p in _PROC.iterdir() if p.name.isdigit()]
    except OSError:
        return ()

    for pid_dir in pids:
        pid = pid_dir.name
        status = _read_proc_status(pid)
        if not status:
            continue
        comm, ppid, nice, rss_pages, threads, state = _read_proc_stat(pid)
        cmdline = _read_proc_cmdline(pid) or comm
        name = (cmdline[:80] if cmdline else comm) or "?"
        try:
            rss = int(status.get("VmRSS", "0 kB").split()[0]) * 1024
        except (ValueError, IndexError):
            rss = rss_pages * 4096
        try:
            vsz = int(status.get("VmSize", "0 kB").split()[0]) * 1024
        except (ValueError, IndexError):
            vsz = 0
        out.append(
            ProcessInfo(
                pid=int(pid),
                ppid=ppid,
                name=name,
                cmdline=cmdline,
                user="",  # filled by callers if needed (requires pwd db)
                rss=rss,
                vsz=vsz,
                cpu_pct=0.0,
                nice=nice,
                threads=threads,
                state=state,
                started=_proc_started(pid),
            )
        )

    out.sort(key=lambda p: p.rss, reverse=True)
    return tuple(out[:top])


# ── battery (best-effort, sysfs + upower) ────────────────────────────────────

def read_battery() -> BatterySample:
    """Battery status from upower; falls back to sysfs."""
    from aegis.core.process import run, which

    if which("upower") is not None:
        r = run(["upower", "-e"], timeout=5)
        if r.ok:
            for line in r.lines():
                if "battery" not in line.lower():
                    continue
                ir = run(["upower", "-i", line], timeout=5)
                if not ir.ok:
                    continue
                info: dict[str, str] = {}
                for ln in ir.lines():
                    if ":" in ln:
                        k, v = ln.split(":", 1)
                        info[k.strip()] = v.strip()
                cap = info.get("capacity", "0").rstrip("%")
                try:
                    cap_pct = float(cap)
                except ValueError:
                    cap_pct = None
                rate_w: float | None = None
                rate = info.get("energy-rate", "")
                try:
                    rate_w = float(rate.split()[0])
                except (ValueError, IndexError):
                    pass
                cycles: int | None = None
                cyc = info.get("charge-cycles", "")
                if cyc.isdigit():
                    cycles = int(cyc)
                return BatterySample(
                    present=True,
                    capacity_pct=cap_pct,
                    state=info.get("state", "—"),
                    rate_w=rate_w,
                    cycles=cycles,
                    health=info.get("capacity", "") + " design",
                    time_to_empty_min=None,
                )

    # sysfs fallback
    base = Path("/sys/class/power_supply")
    if not base.is_dir():
        return BatterySample()
    for dev in base.iterdir():
        try:
            t = (dev / "type").read_text().strip()
        except OSError:
            continue
        if t != "Battery":
            continue
        try:
            cap = int((dev / "capacity").read_text().strip())
            status = (dev / "status").read_text().strip()
            cur = int((dev / "power_now").read_text().strip()) / 1_000_000
        except (OSError, ValueError):
            return BatterySample(present=True)
        return BatterySample(
            present=True,
            capacity_pct=float(cap),
            state=status,
            rate_w=cur if cur else None,
            cycles=None,
            health=None,
            time_to_empty_min=None,
        )

    return BatterySample()