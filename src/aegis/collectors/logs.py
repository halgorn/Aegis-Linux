"""Log collector — systemd journal, /var/log, application logs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from aegis.core.logging import get_logger
from aegis.core.process import run, which

_log = get_logger("collectors.logs")


@dataclass(slots=True, frozen=True)
class LogEntry:
    ts: datetime
    unit: str
    priority: str        # emerg/alert/crit/err/warning/notice/info/debug
    message: str


# ── journalctl ───────────────────────────────────────────────────────────────

def journal_disk_usage() -> str:
    """Return ``journalctl --disk-usage`` output, or ``'—'`` on failure."""
    if which("journalctl") is None:
        return "journalctl not available"
    r = run(["journalctl", "--disk-usage"], timeout=10)
    return r.stdout.strip() if r.ok else "—"


def journal_recent(unit: str = "",
                   priority: str = "warning",
                   since: str = "24h ago",
                   limit: int = 200,
                   ) -> tuple[LogEntry, ...]:
    """Return the last ``limit`` log entries from the journal."""
    if which("journalctl") is None:
        return ()
    argv = [
        "journalctl", "-q", "--no-pager",
        f"--priority={priority}",
        f"--since={since}",
        "-n", str(limit),
        "-o", "short",
    ]
    if unit:
        argv.append(f"--unit={unit}")
    r = run(argv, timeout=15)
    if not r.ok:
        return ()
    return _parse_short(r.stdout)


def journal_follow_available() -> bool:
    return which("journalctl") is not None


# ── /var/log walk ────────────────────────────────────────────────────────────

def list_log_files(root: str = "/var/log") -> tuple[str, ...]:
    """List regular files under ``root`` larger than 1 MiB."""
    import os
    out: list[str] = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            fp = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(fp) > 1024 * 1024:
                    out.append(fp)
            except OSError:
                continue
    return tuple(out)


# ── parsing helpers ─────────────────────────────────────────────────────────

_MONTH = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _parse_short(text: str) -> tuple[LogEntry, ...]:
    """Parse ``journalctl -o short`` output.

    Line format::

        Apr 21 09:35:12 hostname unit[pid]: message…
    """
    out: list[LogEntry] = []
    current_year = datetime.now().year
    for line in text.splitlines():
        if not line:
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        mon, day, hh, mm, ss, rest = parts
        try:
            month = _MONTH.get(mon)
            if not month:
                continue
            ts = datetime(current_year, month, int(day),
                          int(hh), int(mm), int(ss))
        except ValueError:
            continue
        # ``rest`` is "host unit[pid]: msg" — split on first ": "
        if ": " in rest:
            unit_part, msg = rest.split(": ", 1)
            unit = unit_part.split("[")[0].strip()
        else:
            unit, msg = "—", rest
        out.append(LogEntry(ts=ts, unit=unit, priority="info", message=msg))
    return tuple(out)