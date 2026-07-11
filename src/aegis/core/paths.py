"""XDG paths and Aegis data directories.

Single source of truth for where Aegis stores config, logs, cache
and history. Honours ``$XDG_CONFIG_HOME`` / ``$XDG_DATA_HOME`` /
``$XDG_CACHE_HOME`` per the freedesktop spec.

All Aegis code must go through these helpers — never hard-code
``~/.config/aegis`` anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import (
    user_config_dir,
    user_data_dir,
    user_cache_dir,
    user_log_dir,
)

_APP_NAME = "aegis"
_APP_AUTHOR = "aegis-linux"


def xdg_config_dir() -> Path:
    """Return ``$XDG_CONFIG_HOME/aegis`` (created lazily on write)."""
    return Path(user_config_dir(_APP_NAME, _APP_AUTHOR, roaming=False))


def xdg_data_dir() -> Path:
    """Return ``$XDG_DATA_HOME/aegis-linux`` (created lazily on write)."""
    return Path(user_data_dir(_APP_NAME, _APP_AUTHOR, roaming=False))


def xdg_cache_dir() -> Path:
    """Return ``$XDG_CACHE_HOME/aegis-linux`` (created lazily on write)."""
    return Path(user_cache_dir(_APP_NAME, _APP_AUTHOR))


def xdg_log_dir() -> Path:
    """Return ``$XDG_STATE_HOME/aegis-linux/log`` (or fallback)."""
    return Path(user_log_dir(_APP_NAME, _APP_AUTHOR))


def config_file() -> Path:
    """Default JSON config location."""
    return xdg_config_dir() / "config.json"


def history_db() -> Path:
    """SQLite database storing cleanup history / undo log."""
    return xdg_data_dir() / "history.sqlite3"


def metrics_db() -> Path:
    """SQLite database storing monitor time-series (Fase 7)."""
    return xdg_cache_dir() / "metrics.sqlite3"


def plugin_dir() -> Path:
    """User-level plugin drop-in directory."""
    return xdg_data_dir() / "plugins"


def ensure_dirs() -> None:
    """Create all Aegis directories if missing. Idempotent."""
    for d in (xdg_config_dir(), xdg_data_dir(), xdg_cache_dir(),
              xdg_log_dir(), plugin_dir()):
        d.mkdir(parents=True, exist_ok=True)


def is_root() -> bool:
    """True if the current process has uid 0."""
    return os.geteuid() == 0