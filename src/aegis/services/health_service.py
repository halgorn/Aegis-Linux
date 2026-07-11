"""Health service — composite 0–100 score with a list of issues."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from aegis.collectors import disks as disks_col
from aegis.collectors import integrity as integ_col
from aegis.collectors import network as net_col
from aegis.collectors import procfs as proc_col
from aegis.collectors import security as sec_col
from aegis.collectors import startup as startup_col
from aegis.collectors import sysfs as sysfs_col
from aegis.domain.health import HealthIssue, HealthReport, Severity
from aegis.services import backup_service


class HealthService:
    """Aggregate health probes. Each probe is a small function that
    adds :class:`HealthIssue` objects to a :class:`HealthReport`.
    """

    PROBES: tuple[Callable[[HealthReport], None], ...] = ()

    def run(self, *, retention_days: int = 30) -> HealthReport:
        report = HealthReport()
        for probe in self.PROBES:
            try:
                probe(report)
            except Exception:  # noqa: BLE001
                # A failing probe must not poison the report.
                continue
        # Side-effect: prune old backups.
        try:
            backup_service.cleanup_old(retention_days)
        except Exception:  # noqa: BLE001
            pass
        return report

    def to_text(self) -> str:
        return self.run().to_text()


# ── individual probes ──────────────────────────────────────────────────────

def probe_disk_usage(report: HealthReport) -> None:
    for m in disks_col.read_mounts():
        if m.is_full:
            report.add(HealthIssue(
                code="disk.full",
                title=f"Disk almost full: {m.mount}",
                detail=f"{m.used_pct*100:.0f}% of {m.fstype} used "
                       f"({disks_col.used_bytes(m.mount) // 1024**3} GB)",
                severity=Severity.HIGH,
                suggestion="Run the Cleaner tab or expand storage.",
                data={"mount": m.mount, "pct": m.used_pct},
            ))


def probe_memory_pressure(report: HealthReport) -> None:
    m = proc_col.read_meminfo()
    if m.total and m.used_pct >= 0.92:
        report.add(HealthIssue(
            code="ram.pressure",
            title="RAM pressure",
            detail=f"Only {m.available/1024**3:.1f} GB available of "
                   f"{m.total/1024**3:.1f} GB",
            severity=Severity.HIGH,
            suggestion="Identify memory hogs in Monitor > Processes.",
        ))


def probe_swap(report: HealthReport) -> None:
    m = proc_col.read_meminfo()
    if m.swap_total and m.swap_used_pct >= 0.5:
        report.add(HealthIssue(
            code="swap.high",
            title="Swap heavily used",
            detail=f"{m.swap_used_pct*100:.0f}% of swap in use",
            severity=Severity.MEDIUM,
            suggestion="Consider lowering vm.swappiness or adding RAM.",
        ))


def probe_failed_services(report: HealthReport) -> None:
    for unit, state in sec_col.failed_services():
        report.add(HealthIssue(
            code=f"service.failed:{unit}",
            title=f"Failed service: {unit}",
            detail=state,
            severity=Severity.MEDIUM,
            suggestion=f"Investigate with: systemctl status {unit}",
            data={"unit": unit},
        ))


def probe_ssh_keys(report: HealthReport) -> None:
    for issue in sec_col.ssh_key_issues():
        sev = Severity.HIGH if "private" in issue.reason else Severity.MEDIUM
        report.add(HealthIssue(
            code="ssh.perm",
            title=f"SSH permission: {issue.path}",
            detail=issue.reason,
            severity=sev,
            suggestion=f"chmod {oct(issue.expected_mode)[2:]} {issue.path}",
        ))


def probe_ssh_config(report: HealthReport) -> None:
    for f in sec_col.ssh_config_audit():
        report.add(HealthIssue(
            code=f"ssh.config:{f.code}",
            title=f.title,
            detail=f.detail,
            severity=f.severity,
            suggestion=f.suggestion,
        ))


def probe_world_writable(report: HealthReport) -> None:
    files = sec_col.world_writable_files(limit=20)
    if len(files) >= 20:
        report.add(HealthIssue(
            code="fs.world_writable",
            title=f"{len(files)}+ world-writable files in $HOME",
            detail="Files anyone can modify. Common source of exploits.",
            severity=Severity.MEDIUM,
            suggestion="Review and chmod 644 / 600 as appropriate.",
        ))


def probe_old_kernels(report: HealthReport) -> None:
    old = integ_col.old_kernels()
    if len(old) >= 2:
        report.add(HealthIssue(
            code="kernel.old",
            title=f"{len(old)} old kernels installed",
            detail=", ".join(old[:3]),
            severity=Severity.LOW,
            suggestion="Remove via Health > Old Kernels (keeps current + 1).",
        ))


def probe_broken_symlinks(report: HealthReport) -> None:
    broken = integ_col.broken_symlinks(limit=10)
    if broken:
        report.add(HealthIssue(
            code="fs.broken_symlinks",
            title=f"{len(broken)} broken symlinks in $HOME",
            detail="Dangling references cluttering the filesystem.",
            severity=Severity.LOW,
            suggestion="Cleaner can remove them; review before deleting.",
        ))


def probe_orphan_desktop(report: HealthReport) -> None:
    orphans = integ_col.orphan_desktop_entries()
    if len(orphans) >= 3:
        report.add(HealthIssue(
            code="desktop.orphans",
            title=f"{len(orphans)} orphan .desktop entries",
            detail="Menu entries pointing to commands that no longer exist.",
            severity=Severity.LOW,
            suggestion="Remove via Health > Integrity.",
        ))


def probe_load(report: HealthReport) -> None:
    import os
    l1, _, _ = proc_col.read_loadavg()
    cpus = os.cpu_count() or 1
    if l1 > cpus * 2:
        report.add(HealthIssue(
            code="load.high",
            title="High load average",
            detail=f"load1={l1:.2f}, CPUs={cpus}",
            severity=Severity.MEDIUM,
            suggestion="Check top processes in the Monitor tab.",
        ))


def probe_firewall(report: HealthReport) -> None:
    state = net_col.firewall_active()
    if state is False:
        report.add(HealthIssue(
            code="net.firewall_off",
            title="Firewall appears inactive",
            detail="No firewall backend detected as active.",
            severity=Severity.HIGH,
            suggestion="Enable ufw / firewalld / nftables.",
        ))


def probe_persistence(report: HealthReport) -> None:
    for f in sec_col.persistence_findings():
        report.add(HealthIssue(
            code=f"persist:{f.code}",
            title=f.title,
            detail=f.detail,
            severity=f.severity,
            suggestion=f.suggestion,
        ))


def probe_temps(report: HealthReport) -> None:
    for t in sysfs_col.read_temperatures():
        if t.celsius >= 85:
            report.add(HealthIssue(
                code="hw.temp_high",
                title=f"{t.label} hot",
                detail=f"{t.celsius:.0f}°C",
                severity=Severity.HIGH,
                suggestion="Check airflow / fans / thermal paste.",
                data={"sensor": t.label, "c": t.celsius},
            ))


# Register probes
HealthService.PROBES = (
    probe_disk_usage,
    probe_memory_pressure,
    probe_swap,
    probe_failed_services,
    probe_ssh_keys,
    probe_ssh_config,
    probe_world_writable,
    probe_old_kernels,
    probe_broken_symlinks,
    probe_orphan_desktop,
    probe_load,
    probe_firewall,
    probe_persistence,
    probe_temps,
)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``aegis --doctor``."""
    import sys
    sys.argv = argv if argv is not None else sys.argv
    print(HealthService().to_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())