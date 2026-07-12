"""Command-line entry point for Aegis Linux.

Top-level commands:

* ``aegis``                          → launch the GUI (default).
* ``aegis --doctor``                 → one-shot health report.
* ``aegis --headless-clean ID ...``  → run the cleaner headless.
* ``aegis scan <category> [--json]`` → run any single scanner and
                                       print the result as JSON.

This module is intentionally thin. All real work lives in the
``services`` package; the CLI is just an adapter.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aegis",
        description="Aegis Linux - performance & security suite",
    )
    p.add_argument(
        "--no-gui",
        action="store_true",
        help="force headless mode (no Qt window)",
    )
    p.add_argument(
        "--tk",
        action="store_true",
        help="use the Tk fallback UI instead of Qt6",
    )
    p.add_argument(
        "--doctor",
        action="store_true",
        help="run a one-shot health report and exit",
    )
    p.add_argument(
        "--headless-clean",
        nargs="+",
        metavar="TARGET_ID",
        help="clean the given target IDs without GUI",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="preview actions without executing them",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="override config file path",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    sub = p.add_subparsers(dest="command")
    scan_p = sub.add_parser(
        "scan", help="run a single scanner and print the result as JSON",
    )
    from aegis.core.scanners import list_scanners
    scan_p.add_argument(
        "category", choices=list_scanners(),
        help="which scanner to run",
    )
    scan_p.add_argument(
        "--target", action="append", default=[],
        help="(cleaner) target ID; repeat for multiple. Empty = all.",
    )
    scan_p.add_argument(
        "--lines", type=int, default=200,
        help="(logs) how many lines to fetch",
    )
    scan_p.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false",
        help="(cleaner) actually delete; without this flag it's a dry run",
    )
    scan_p.set_defaults(dry_run=True)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Lazy imports so --help stays fast and tkinter is optional at CLI.
    from aegis.core.logging import setup_logging
    from aegis.core.paths import ensure_dirs

    setup_logging(args.log_level)
    ensure_dirs()

    if args.command == "scan":
        from aegis.core.scanners import run_scan
        return run_scan(args.category, args)

    if args.doctor:
        from aegis.services.health_service import HealthService
        print(HealthService().to_text())
        return 0

    if args.headless_clean:
        from aegis.services.cleaner_service import CleanerService
        result = CleanerService().run(args.headless_clean, dry_run=args.dry_run)
        print(result.to_text())
        return 0 if result.ok else 1

    if args.no_gui:
        print("error: --no-gui given but no command selected", file=sys.stderr)
        return 2

    # Default: launch GUI.
    if args.tk:
        try:
            from aegis.ui.app import launch_gui as tk_launch
            return tk_launch()
        except ImportError as exc:
            print(f"error: Tk GUI not available: {exc}", file=sys.stderr)
            return 3

    try:
        from aegis.ui.app_qt import launch_gui
    except ImportError as exc:
        print(f"error: Qt GUI not available: {exc}", file=sys.stderr)
        print("hint: install PyQt6 or use --tk / --doctor / --headless-clean "
              "or `aegis scan <category>`", file=sys.stderr)
        return 3

    return launch_gui()


if __name__ == "__main__":
    raise SystemExit(main())