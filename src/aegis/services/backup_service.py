"""Backup / undo / restore-point service.

Before any destructive operation the cleaner service calls
:func:`BackupService.snapshot_files`. Snapshots are tarballs in
``$XDG_DATA_HOME/aegis-linux/backups/`` retained for
``config.backup_retention_days`` days.

The :class:`BackupService` is intentionally small — just enough
metadata to undo file removals (not full system snapshots).
BTRFS/ZFS snapshots are a separate feature (handled via
``btrfs`` / ``zfs`` CLIs when available).
"""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.paths import xdg_data_dir

_log = get_logger("services.backup")


@dataclass(slots=True, frozen=True)
class BackupEntry:
    """One snapshot of one file (or one dir's contents)."""

    backup_id: str
    original_path: str
    backup_path: str
    created_at: datetime


def _backup_root() -> Path:
    p = xdg_data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def snapshot_files(paths: Iterable[str],
                   *, label: str = "") -> tuple[BackupEntry, ...]:
    """Copy each path (file or dir) into a tarball and return metadata.

    Returns one :class:`BackupEntry` per existing path.
    """
    backup_root = _backup_root()
    backup_id = f"{label or 'snap'}-{int(time.time())}"
    archive = backup_root / f"{backup_id}.tar.gz"

    existing = [p for p in paths if os.path.exists(p)]
    if not existing:
        return ()

    out: list[BackupEntry] = []
    with tarfile.open(archive, "w:gz") as tf:
        for p in existing:
            try:
                tf.add(p, arcname=os.path.basename(p))
            except OSError as exc:
                _log.warning("snapshot skip %s: %s", p, exc)
                continue
            out.append(BackupEntry(
                backup_id=backup_id,
                original_path=p,
                backup_path=str(archive),
                created_at=datetime.utcnow(),
            ))
    return tuple(out)


def restore(backup: BackupEntry) -> bool:
    """Extract ``backup`` to its original location. Overwrites."""
    if not os.path.isfile(backup.backup_path):
        return False
    target_dir = os.path.dirname(backup.original_path) or "."
    try:
        with tarfile.open(backup.backup_path, "r:gz") as tf:
            tf.extractall(target_dir)
        return True
    except (tarfile.TarError, OSError) as exc:
        _log.error("restore %s failed: %s", backup.backup_path, exc)
        return False


def cleanup_old(retention_days: int = 30) -> int:
    """Delete backups older than ``retention_days``. Returns count removed."""
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for f in _backup_root().iterdir():
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def list_backups() -> tuple[BackupEntry, ...]:
    out: list[BackupEntry] = []
    for f in sorted(_backup_root().glob("*.tar.gz"), reverse=True):
        try:
            ts = datetime.fromtimestamp(f.stat().st_mtime)
        except OSError:
            continue
        out.append(BackupEntry(
            backup_id=f.stem,
            original_path="(snapshot)",
            backup_path=str(f),
            created_at=ts,
        ))
    return tuple(out)