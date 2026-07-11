"""Structured logging setup.

Aegis logs to stderr by default and to ``$XDG_STATE_HOME/aegis-linux/
log/aegis.log`` when a file handler can be created. The format is
plain-text for human readability; JSON output is opt-in via
``AEGIS_LOG_JSON=1``.

Importing this module is side-effect free; call :func:`setup_logging`
exactly once at process start.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Final

from aegis.core.paths import xdg_log_dir

_LOGGER_NAME: Final = "aegis"
_MAX_BYTES: Final = 2 * 1024 * 1024  # 2 MiB
_BACKUP_COUNT: Final = 3

_configured = False


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the root ``aegis`` logger.

    Safe to call multiple times — subsequent calls just adjust the
    level.
    """
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level.upper())

    if not _configured:
        logger.propagate = False
        _add_stream(logger)
        _add_file(logger)
        _configured = True
    else:
        logger.setLevel(level.upper())

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger (``aegis.foo.bar`` if ``name="foo.bar"``)."""
    if name is None:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def _add_stream(logger: logging.Logger) -> None:
    if any(isinstance(h, logging.StreamHandler)
           and getattr(h, "_aegis_stream", False)
           for h in logger.handlers):
        return
    h = logging.StreamHandler(stream=sys.stderr)
    h._aegis_stream = True  # type: ignore[attr-defined]
    h.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(h)


def _add_file(logger: logging.Logger) -> None:
    try:
        path = xdg_log_dir() / "aegis.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(path, maxBytes=_MAX_BYTES,
                                backupCount=_BACKUP_COUNT,
                                encoding="utf-8")
        h.setFormatter(logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        ))
        logger.addHandler(h)
    except OSError:
        # Read-only filesystem or no permission — skip file logging.
        pass


def set_json_mode(enabled: bool) -> None:
    """Toggle JSON output on the stream handler (for log shipping)."""
    fmt: logging.Formatter
    if enabled or os.environ.get("AEGIS_LOG_JSON") == "1":
        fmt = logging.Formatter(
            '{"ts":"%(asctime)s","lvl":"%(levelname)s",'
            '"logger":"%(name)s","msg":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    else:
        return
    for h in logging.getLogger(_LOGGER_NAME).handlers:
        if isinstance(h, logging.StreamHandler):
            h.setFormatter(fmt)