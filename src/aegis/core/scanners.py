"""``aegis scan <category>`` — run any individual scanner from the CLI.

Each scanner returns a dataclass; ``asdict()`` plus ``json.dumps()``
gets us a stable JSON shape without per-service serializers. The
shape is documented in :func:`_scan_one` (one line per scanner).
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from typing import Callable

from aegis.core.logging import get_logger

_log = get_logger(__name__)


# ── per-scanner adapters ──────────────────────────────────────────────────────
# Each adapter returns a dataclass (or a small dict) that asdict()
# can serialise. Keeping the list here makes it trivial to add a new
# scanner: drop a fn + key into SCANNERS, the CLI just works.

def _adapter_health(args):
    from aegis.services.health_service import HealthService
    return HealthService().run()


def _adapter_security(args):
    from aegis.services.security_service import SecurityService
    return SecurityService().scan()


def _adapter_cleaner(args):
    from aegis.services.cleaner_service import CleanerService
    ids = args.target or []  # may be empty -> preview all
    return CleanerService().run(
        target_ids=ids, dry_run=args.dry_run, create_backup=not args.dry_run,
    )


def _adapter_disks(args):
    from aegis.services.disks_service import scan
    return scan()


def _adapter_network(args):
    from aegis.services.network_service import scan
    return scan()


def _adapter_drivers(args):
    from aegis.services.drivers_service import scan
    return scan()


def _adapter_packages(args):
    from aegis.services.packages_service import scan
    return scan()


def _adapter_startup(args):
    from aegis.services.startup_service import scan
    return scan()


def _adapter_logs(args):
    from aegis.services.logs_service import tail
    return tail(lines=args.lines or 200)


def _adapter_performance(args):
    from aegis.collectors import procfs
    return procfs.list_processes(top=30)


# Map of CLI name -> (adapter_fn, dataclass?, schema description)
SCANNERS: dict[str, tuple[Callable, str]] = {
    "health":     (_adapter_health,     "HealthReport - score, grade, issues[]"),
    "security":   (_adapter_security,   "[SecurityFinding] - code, severity, detail"),
    "cleaner":    (_adapter_cleaner,    "CleanResult - records[], bytes_freed, ok"),
    "disks":      (_adapter_disks,      "DisksReport - filesystems[], smart[]"),
    "network":    (_adapter_network,    "NetworkReport - interfaces[], listening[]"),
    "drivers":    (_adapter_drivers,    "DriversReport - modules[]"),
    "packages":   (_adapter_packages,   "PackagesReport - packages[]"),
    "startup":    (_adapter_startup,    "StartupReport - items[]"),
    "logs":       (_adapter_logs,       "LogsReport - lines[]"),
    "performance": (_adapter_performance, "[Process] - pid, name, cpu_pct, rss, user"),
}


def _to_jsonable(obj):
    """Recursively convert dataclasses + enums to plain dicts/lists/strings.

    Falls back to str(obj) for anything unknown so the CLI never crashes
    on a weird field — bad data should produce ugly JSON, not a traceback.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # Enum, datetime, Path, etc — stringify rather than crash.
    try:
        return obj.value  # Enum
    except AttributeError:
        pass
    try:
        return obj.isoformat()  # datetime / date
    except AttributeError:
        pass
    return str(obj)


def run_scan(category: str, args) -> int:
    """Dispatch a single scan and print JSON to stdout. Exit 0 on success."""
    if category not in SCANNERS:
        print(f"error: unknown scanner '{category}'. "
              f"Available: {', '.join(sorted(SCANNERS))}", file=sys.stderr)
        return 2
    fn, _desc = SCANNERS[category]
    try:
        result = fn(args)
    except Exception as e:  # noqa: BLE001
        _log.exception("scan %s failed", category)
        print(json.dumps({"error": str(e), "scanner": category}, indent=2))
        return 1
    print(json.dumps(_to_jsonable(result), indent=2, ensure_ascii=False))
    return 0


def list_scanners() -> list[str]:
    return sorted(SCANNERS)