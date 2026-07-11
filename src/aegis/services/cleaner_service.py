"""Cleaner service — turn a list of target IDs into a :class:`CleanResult`.

The CLI calls :meth:`CleanerService.run`. The GUI builds a plan
(via :meth:`build_plan`) first, asks the user to confirm, then calls
:meth:`execute_plan`. Both flows share the same executor.
"""

from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aegis.collectors import disks as disks_col
from aegis.collectors import filesystem as fs_col
from aegis.collectors import packages as pkg_col
from aegis.core.logging import get_logger
from aegis.core.privileges import elevate
from aegis.domain.cleaner import (
    CleanCategory,
    CleanKind,
    CleanPlan,
    CleanRecord,
    CleanResult,
    CleanTarget,
)
from aegis.rules.cleaner_rules import all_targets, target_by_id

_log = get_logger("services.cleaner")


# ── plan builder ─────────────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class PlanEstimate:
    """Summary of what ``build_plan`` would do."""

    plan: CleanPlan
    total_bytes: int
    unknown_size: tuple[str, ...]


def build_plan(target_ids: list[str],
               *,
               dry_run: bool = False,
               create_backup: bool = True) -> PlanEstimate:
    """Resolve target IDs and estimate sizes in parallel-ish (sequential
    for safety; sizes need an actual walk)."""
    targets: list[CleanTarget] = []
    for tid in target_ids:
        t = target_by_id(tid)
        if t is None:
            _log.warning("unknown target id: %s", tid)
            continue
        targets.append(t)

    total = 0
    unknowns: list[str] = []
    for t in targets:
        if t.estimated_size:
            total += t.estimated_size
            continue
        size = _estimate_target_size(t)
        if size is None:
            unknowns.append(t.id)
        else:
            # Patch the dataclass via object.__setattr__ (frozen).
            object.__setattr__(t, "estimated_size", size)
            total += size

    return PlanEstimate(
        plan=CleanPlan(targets=targets, dry_run=dry_run,
                       create_backup=create_backup),
        total_bytes=total,
        unknown_size=tuple(unknowns),
    )


def _estimate_target_size(t: CleanTarget) -> int | None:
    """Walk target paths to estimate total bytes. Returns ``None`` for
    EXEC / unknown targets."""
    if t.kind in (CleanKind.EXEC,) or not t.paths:
        return None
    total = 0
    for p in t.paths:
        if os.path.isfile(p):
            try:
                total += os.path.getsize(p)
            except OSError:
                continue
        elif os.path.isdir(p):
            total += disks_col.dir_size(p)
    return total


# ── executor ────────────────────────────────────────────────────────────────

def execute_plan(plan: CleanPlan,
                 *,
                 cancel: threading.Event | None = None,
                 on_record: "callable[[CleanRecord], None] | None" = None,
                 ) -> CleanResult:
    """Execute every target in ``plan`` sequentially. Honours ``cancel``."""
    from aegis.services import backup_service

    result = CleanResult()
    for t in plan.targets:
        if cancel is not None and cancel.is_set():
            break
        started = datetime.utcnow()
        try:
            if plan.create_backup and t.reversible:
                backup_service.snapshot_files(t.paths, label=t.id)

            freed, files = _execute_target(t, plan.dry_run, cancel=cancel)
            record = CleanRecord(
                target_id=t.id, label=t.label,
                bytes_freed=freed, files_removed=files,
                started_at=started, finished_at=datetime.utcnow(),
                ok=True,
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("target %s failed", t.id)
            record = CleanRecord(
                target_id=t.id, label=t.label,
                bytes_freed=0, files_removed=0,
                started_at=started, finished_at=datetime.utcnow(),
                ok=False, error=str(exc),
            )
        result.records.append(record)
        if on_record is not None:
            try:
                on_record(record)
            except Exception:  # noqa: BLE001
                _log.exception("on_record callback raised")
    result.finished_at = datetime.utcnow()
    return result


def _execute_target(t: CleanTarget,
                    dry_run: bool,
                    *,
                    cancel: threading.Event | None) -> tuple[int, int]:
    """Return ``(bytes_freed, files_removed)``."""
    if dry_run:
        return _estimate_target_size(t) or 0, 0

    if t.kind == CleanKind.DELETE_CONTENTS:
        return _delete_contents(t, cancel)
    if t.kind == CleanKind.DELETE_FILES:
        return _delete_files(t, cancel)
    if t.kind == CleanKind.TRUNCATE:
        return _truncate(t, cancel)
    if t.kind == CleanKind.EXEC:
        return _execute_command(t)
    return 0, 0


def _delete_contents(t: CleanTarget,
                     cancel: threading.Event | None) -> tuple[int, int]:
    freed = 0
    files = 0
    for p in t.paths:
        if cancel is not None and cancel.is_set():
            break
        if not os.path.isdir(p):
            continue
        for fp in fs_col.iter_files(p, cancel=cancel):
            try:
                freed += os.path.getsize(fp)
            except OSError:
                continue
            files += 1
        try:
            shutil.rmtree(p, ignore_errors=True)
        except OSError as exc:
            _log.warning("rmtree %s: %s", p, exc)
    return freed, files


def _delete_files(t: CleanTarget,
                  cancel: threading.Event | None) -> tuple[int, int]:
    freed = 0
    files = 0
    for p in t.paths:
        if cancel is not None and cancel.is_set():
            break
        if not os.path.isfile(p):
            continue
        try:
            freed += os.path.getsize(p)
        except OSError:
            continue
        files += 1
        try:
            os.remove(p)
        except OSError as exc:
            _log.warning("remove %s: %s", p, exc)
    return freed, files


def _truncate(t: CleanTarget,
              cancel: threading.Event | None) -> tuple[int, int]:
    freed = 0
    files = 0
    for p in t.paths:
        if cancel is not None and cancel.is_set():
            break
        if not os.path.isfile(p):
            continue
        try:
            freed += os.path.getsize(p)
        except OSError:
            continue
        files += 1
        try:
            with open(p, "wb") as fp:
                fp.truncate(0)
        except OSError as exc:
            _log.warning("truncate %s: %s", p, exc)
    return freed, files


def _execute_command(t: CleanTarget) -> tuple[int, int]:
    """EXEC targets. The first argv element of ``t.command`` is one of:

    * a real binary → call directly (sudo if needed);
    * ``__internal__`` → dispatch to a Python helper.
    """
    if not t.command:
        return 0, 0

    if t.command[0] == "__internal__":
        return _internal_command(t)

    if t.needs_root:
        r = elevate(list(t.command), reason=f"aegis: {t.label}")
    else:
        from aegis.core.process import run
        r = run(list(t.command), timeout=300)
    if not r.ok:
        raise RuntimeError(f"{' '.join(t.command)} failed: {r.stderr.strip()}")
    return 0, 0


def _internal_command(t: CleanTarget) -> tuple[int, int]:
    name = t.command[1]
    if name == "snap_old_revisions":
        for snap_name, rev in pkg_col.snap_old_revisions():
            elevate(["snap", "remove", "--revision", rev, snap_name],
                    reason=f"remove snap {snap_name} rev {rev}")
        return 0, 0
    if name == "pyc_clean":
        return _walk_clean_pyc()
    if name == "macos_clean":
        return _walk_clean_artifacts((".DS_Store",), ("__MACOSX",))
    if name == "win_clean":
        return _walk_clean_artifacts(("Thumbs.db", "desktop.ini"), ())
    raise RuntimeError(f"unknown internal command: {name}")


def _walk_clean_pyc() -> tuple[int, int]:
    freed = 0
    files = 0
    home = os.path.expanduser("~")
    for dirpath, dirnames, filenames in os.walk(home, followlinks=False):
        if "__pycache__" in dirnames:
            target = os.path.join(dirpath, "__pycache__")
            try:
                freed += disks_col.dir_size(target)
            except OSError:
                pass
            try:
                shutil.rmtree(target, ignore_errors=True)
                files += 1
            except OSError:
                pass
            dirnames.remove("__pycache__")
        for fname in filenames:
            if fname.endswith(".pyc"):
                fp = os.path.join(dirpath, fname)
                try:
                    freed += os.path.getsize(fp)
                    os.remove(fp)
                    files += 1
                except OSError:
                    continue
    return freed, files


def _walk_clean_artifacts(file_names: tuple[str, ...],
                          dir_names: tuple[str, ...]
                          ) -> tuple[int, int]:
    freed = 0
    files = 0
    home = os.path.expanduser("~")
    for dirpath, dirnames, filenames in os.walk(home, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if fname in file_names:
                fp = os.path.join(dirpath, fname)
                try:
                    freed += os.path.getsize(fp)
                    os.remove(fp)
                    files += 1
                except OSError:
                    continue
        for d in list(dirnames):
            if d in dir_names:
                target = os.path.join(dirpath, d)
                try:
                    freed += disks_col.dir_size(target)
                    shutil.rmtree(target, ignore_errors=True)
                    files += 1
                except OSError:
                    continue
                dirnames.remove(d)
    return freed, files


# ── public facade ───────────────────────────────────────────────────────────

class CleanerService:
    """Stateless façade used by CLI / GUI."""

    def run(self, target_ids: list[str], *,
            dry_run: bool = False,
            create_backup: bool = True,
            cancel: threading.Event | None = None,
            on_record=None) -> CleanResult:
        est = build_plan(target_ids, dry_run=dry_run,
                         create_backup=create_backup)
        return execute_plan(est.plan, cancel=cancel, on_record=on_record)