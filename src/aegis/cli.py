"""Command-line entry point for Aegis Linux.

Provides three top-level commands:

* ``aegis``            → launch the GUI (default).
* ``aegis --doctor``   → print a one-shot health report to stdout.
* ``aegis --headless-clean TARGET_ID [...]``
                        → run the cleaner service without a UI.

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
        description="Aegis Linux — performance & security suite",
    )
    p.add_argument(
        "--no-gui",
        action="store_true",
        help="force headless mode (no Tk window)",
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
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Lazy imports so --help stays fast and tkinter is optional at CLI.
    from aegis.core.logging import setup_logging
    from aegis.core.paths import xdg_config_dir, ensure_dirs

    setup_logging(args.log_level)
    ensure_dirs()

    if args.doctor:
        from aegis.services.health_service import HealthService

        report = HealthService().run()
        print(report.to_text())
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
    try:
        from aegis.ui.app import launch_gui
    except ImportError as exc:
        print(f"error: GUI not available: {exc}", file=sys.stderr)
        print("hint: install tkinter or use --doctor / --headless-clean", file=sys.stderr)
        return 3

    return launch_gui()


if __name__ == "__main__":
    raise SystemExit(main())