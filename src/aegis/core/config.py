"""Persistent JSON configuration.

The config lives at ``$XDG_CONFIG_HOME/aegis/config.json`` and is
loaded lazily, mutated through a dataclass, and written back
atomically (write-temp + rename) to avoid corruption on crash.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from aegis.core.paths import config_file

_DEFAULTS: dict[str, Any] = {
    "theme": "dark",                      # dark | light
    "accent": "blue",                     # blue | green | mauve | pink
    "autostart": False,                   # launch on login
    "minimize_to_tray": True,
    "confirm_destructive": True,
    "dry_run_by_default": False,
    "create_backup_before_clean": True,
    "backup_retention_days": 30,
    "monitor_refresh_hz": 1.0,
    "monitor_history_minutes": 10,
    "scan_skip_paths": ["/proc", "/sys", "/dev", "/run", "/snap"],
    "scan_extra_paths": [],
    "scan_follow_symlinks": False,
    "enable_telemetry": False,
    "log_level": "INFO",
    "ai_provider": "offline",             # offline | local | cloud
    "ai_model": "",
    "locale": "",
}


@dataclass(slots=True)
class Config:
    """In-memory representation of ``config.json``.

    Unknown keys are kept in :attr:`_extra` and re-serialised
    unchanged, so config files are forward-compatible.
    """

    theme: str = "dark"
    accent: str = "blue"
    autostart: bool = False
    minimize_to_tray: bool = True
    confirm_destructive: bool = True
    dry_run_by_default: bool = False
    create_backup_before_clean: bool = True
    backup_retention_days: int = 30
    monitor_refresh_hz: float = 1.0
    monitor_history_minutes: int = 10
    scan_skip_paths: list[str] = field(default_factory=lambda: list(_DEFAULTS["scan_skip_paths"]))
    scan_extra_paths: list[str] = field(default_factory=list)
    scan_follow_symlinks: bool = False
    enable_telemetry: bool = False
    log_level: str = "INFO"
    ai_provider: str = "offline"
    ai_model: str = ""
    locale: str = ""
    _extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Read config from disk; return defaults if missing."""
        p = path or config_file()
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        kw: dict[str, Any] = {k: v for k, v in raw.items() if k in known}
        extra = {k: v for k, v in raw.items() if k not in known}
        cfg = cls(**kw)
        cfg._extra = extra
        return cfg

    def save(self, path: Path | None = None) -> None:
        """Atomically write config back to disk."""
        p = path or config_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        # Drop the private field from the on-disk JSON.
        data.pop("_extra", None)
        data.update(self._extra)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".aegis-cfg-", suffix=".json", dir=str(p.parent)
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2, ensure_ascii=False)
            os.replace(tmp_path, p)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style read for unknown keys without warnings."""
        if key in self._extra:
            return self._extra[key]
        if key in _DEFAULTS:
            return getattr(self, key)
        return default

    def set_extra(self, key: str, value: Any) -> None:
        self._extra[key] = value