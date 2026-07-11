"""Performance service — recommendations based on current state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from aegis.collectors import procfs as proc_col
from aegis.collectors import sysfs as sysfs_col
from aegis.core.logging import get_logger

_log = get_logger("services.performance")


@dataclass(slots=True, frozen=True)
class Tuning:
    """A single performance recommendation."""

    code: str
    title: str
    detail: str
    command: tuple[str, ...]
    impact: str               # low / medium / high
    reversible: bool = True


class PerformanceService:
    """Inspect the system and emit a list of recommended tunings."""

    def recommendations(self) -> tuple[Tuning, ...]:
        out: list[Tuning] = []
        out.extend(_cpu_recommendations())
        out.extend(_memory_recommendations())
        out.extend(_io_recommendations())
        return tuple(out)


def _cpu_recommendations() -> Iterable[Tuning]:
    govs = sysfs_col.cpu_governors()
    if not govs:
        return ()
    current = set(govs.values())
    avail = set(sysfs_col.cpu_available_governors())
    # If all cores on "performance" on a laptop battery, suggest powersave.
    if current == {"performance"} and "powersave" in avail:
        yield Tuning(
            code="cpu.gov_performance",
            title="CPU governor is performance",
            detail="On battery this drains fast; consider 'schedutil' or "
                   "'powersave' for normal use.",
            command=("cpupower", "frequency-set", "-g", "schedutil"),
            impact="medium",
        )
    # Show current governor in any case.
    yield Tuning(
        code="cpu.gov_info",
        title=f"CPU governor: {', '.join(sorted(current))}",
        detail="Available: " + ", ".join(sorted(avail)),
        command=(),
        impact="low",
    )


def _memory_recommendations() -> Iterable[Tuning]:
    swappiness = sysfs_col.read_sysctl("vm/swappiness", "60")
    m = proc_col.read_meminfo()
    if swappiness > 30 and m.total > 8 * 1024**3:
        yield Tuning(
            code="vm.swappiness",
            title=f"swappiness={swappiness} (high for an SSD box)",
            detail="Recommended: 10 for SSDs, 60 for HDDs, 1 for servers.",
            command=("sysctl", "-w", "vm.swappiness=10"),
            impact="low",
        )


def _io_recommendations() -> Iterable[Tuning]:
    for dev, sched in sysfs_col.io_schedulers().items():
        # NVMe: mq-deadline is fine; warn on 'cfq' or unknown.
        if "cfq" in sched or "noop" in sched and dev.startswith("nv"):
            yield Tuning(
                code=f"io.sched:{dev}",
                title=f"{dev} scheduler: {sched}",
                detail="mq-deadline or kyber recommended for NVMe.",
                command=(),
                impact="low",
            )