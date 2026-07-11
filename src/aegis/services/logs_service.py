"""Recent log lines from journald (preferred) or syslog."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class LogsReport:
    lines: list[str] = field(default_factory=list)
    source: str = ""


def tail(lines: int = 200) -> LogsReport:
    if shutil.which("journalctl"):
        try:
            r = subprocess.run(
                ["journalctl", "--no-pager", "-n", str(lines),
                 "-o", "short"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if r.stdout:
                return LogsReport(lines=r.stdout.splitlines(), source="journald")
        except (subprocess.TimeoutExpired, OSError):
            pass
    for path in ("/var/log/syslog", "/var/log/messages"):
        try:
            text = open(path, errors="replace").read()
        except OSError:
            continue
        return LogsReport(lines=text.splitlines()[-lines:], source=path)
    return LogsReport(lines=["No log source available."], source="none")