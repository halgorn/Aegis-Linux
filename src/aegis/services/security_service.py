"""Security service — focused scanner that returns a list of findings
the UI can sort / filter."""

from __future__ import annotations

from collections.abc import Iterable

from aegis.collectors import integrity as integ_col
from aegis.collectors import network as net_col
from aegis.collectors import security as sec_col
from aegis.domain.health import Severity
from aegis.domain.security import SecurityFinding


def _permission_to_finding(p) -> SecurityFinding:
    sev = Severity.HIGH if "private" in p.reason else Severity.MEDIUM
    return SecurityFinding(
        code="ssh.perm",
        title=f"SSH permission: {p.path}",
        detail=p.reason,
        severity=sev,
        suggestion=f"chmod {oct(p.expected_mode)[2:]} {p.path}",
    )


def _orphan_to_finding(file: str, cmd: str) -> SecurityFinding:
    return SecurityFinding(
        code="desktop.orphan",
        title=f"Orphan .desktop: {file}",
        detail=f"Exec command not found: {cmd}",
        severity=Severity.LOW,
        suggestion="Remove the .desktop file or fix the Exec path.",
    )


class SecurityService:
    """Aggregate the security collectors and return findings."""

    def scan(self) -> tuple[SecurityFinding, ...]:
        out: list[SecurityFinding] = []
        out.extend(_permission_to_finding(p) for p in sec_col.ssh_key_issues())
        out.extend(sec_col.ssh_config_audit())
        out.extend(sec_col.persistence_findings())
        out.extend(self._ww_findings())
        out.extend(self._listeners_findings())
        out.extend(self._firewall_findings())
        out.extend(_orphan_to_finding(f, c) for f, c in
                   integ_col.orphan_desktop_entries())
        return tuple(out)

    @staticmethod
    def _ww_findings() -> Iterable[SecurityFinding]:
        files = sec_col.world_writable_files(limit=20)
        if not files:
            return ()
        yield SecurityFinding(
            code="fs.world_writable",
            title=f"{len(files)} world-writable file(s) in $HOME",
            detail="\n".join(files[:5]) + ("\n…" if len(files) > 5 else ""),
            severity=Severity.MEDIUM,
            suggestion="chmod 644 on files, 755 on directories.",
        )

    @staticmethod
    def _listeners_findings() -> Iterable[SecurityFinding]:
        out: list[SecurityFinding] = []
        # Ports we wouldn't normally expect on a desktop system.
        sensitive = {22, 23, 3389, 5900, 445, 139}
        for p in net_col.listening_ports():
            try:
                port = int(p.local.rsplit(":", 1)[-1])
            except ValueError:
                continue
            if port in sensitive:
                out.append(SecurityFinding(
                    code=f"net.port_sensitive:{port}",
                    title=f"Sensitive port open: {port}",
                    detail=f"{p.proto} {p.local} ({p.process})",
                    severity=Severity.MEDIUM,
                    suggestion="Disable service or restrict via firewall.",
                ))
        return tuple(out)

    @staticmethod
    def _firewall_findings() -> Iterable[SecurityFinding]:
        state = net_col.firewall_active()
        if state is False:
            yield SecurityFinding(
                code="net.firewall_off",
                title="Firewall inactive",
                detail="No firewall backend reports as active.",
                severity=Severity.HIGH,
                suggestion="Enable ufw/firewalld or add nftables rules.",
            )