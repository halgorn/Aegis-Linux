"""Unit tests for cleaner_service."""

from __future__ import annotations

import os

import pytest

from aegis.services.cleaner_service import (
    CleanerService, _estimate_target_size, build_plan, execute_plan,
)
from aegis.services import backup_service


def _populate_home(home: str) -> None:
    """Write some realistic cache contents in fake home."""
    cache = os.path.join(home, ".cache", "pip")
    os.makedirs(cache, exist_ok=True)
    for i in range(3):
        with open(os.path.join(cache, f"f{i}.bin"), "wb") as fp:
            fp.write(b"x" * 1024)


class TestBuildPlan:
    def test_resolves_targets(self, tmp_home):
        _populate_home(tmp_home)
        est = build_plan(["pip_cache"], dry_run=True)
        assert len(est.plan.targets) == 1
        assert est.plan.targets[0].id == "pip_cache"
        assert est.total_bytes >= 3072  # 3 * 1024

    def test_unknown_target_skipped(self, tmp_home):
        est = build_plan(["pip_cache", "nonexistent_target"], dry_run=True)
        assert len(est.plan.targets) == 1
        assert est.plan.targets[0].id == "pip_cache"

    def test_empty_targets(self, tmp_home):
        est = build_plan([], dry_run=True)
        assert len(est.plan.targets) == 0
        assert est.total_bytes == 0


class TestEstimateTargetSize:
    def test_missing_path_zero(self, tmp_home):
        from aegis.domain.cleaner import CleanTarget, CleanKind, CleanCategory
        t = CleanTarget(id="t", label="t", description="d",
                        category=CleanCategory.SYSTEM,
                        kind=CleanKind.DELETE_CONTENTS,
                        paths=(os.path.join(tmp_home, "nope"),))
        assert _estimate_target_size(t) == 0

    def test_directory(self, tmp_home):
        from aegis.domain.cleaner import CleanTarget, CleanKind, CleanCategory
        _populate_home(tmp_home)
        t = CleanTarget(id="t", label="t", description="d",
                        category=CleanCategory.SYSTEM,
                        kind=CleanKind.DELETE_CONTENTS,
                        paths=(os.path.join(tmp_home, ".cache", "pip"),))
        assert _estimate_target_size(t) == 3072


class TestExecutePlanDryRun:
    def test_dry_run_no_files_removed(self, tmp_home):
        _populate_home(tmp_home)
        cache = os.path.join(tmp_home, ".cache", "pip")
        before = sorted(os.listdir(cache))
        svc = CleanerService()
        result = svc.run(["pip_cache"], dry_run=True)
        assert result.ok
        after = sorted(os.listdir(cache))
        assert before == after
        # In dry-run the estimate was returned as bytes_freed
        assert result.bytes_freed >= 3072


class TestExecutePlanReal:
    def test_delete_contents(self, tmp_home):
        _populate_home(tmp_home)
        cache = os.path.join(tmp_home, ".cache", "pip")
        svc = CleanerService()
        result = svc.run(["pip_cache"], dry_run=False, create_backup=False)
        assert result.ok
        # After run, the directory should be gone (rmtree removes parent too)
        assert not os.path.exists(cache)
        # Counts in the record
        rec = result.records[0]
        assert rec.ok
        assert rec.files_removed == 3

    def test_delete_file(self, tmp_home):
        path = os.path.join(tmp_home, ".local", "share",
                            "recently-used.xbel")
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            f.write("data")
        svc = CleanerService()
        result = svc.run(["recent_files"], dry_run=False, create_backup=False)
        assert result.ok
        assert not os.path.exists(path)

    def test_truncate(self, tmp_home):
        path = os.path.join(tmp_home, ".bash_history")
        with open(path, "w") as f:
            f.write("cmd1\ncmd2\n")
        svc = CleanerService()
        result = svc.run(["shell_history"], dry_run=False, create_backup=False)
        assert result.ok
        # File should still exist but be empty
        assert os.path.exists(path)
        assert os.path.getsize(path) == 0

    def test_truncate_with_backup(self, tmp_home):
        path = os.path.join(tmp_home, ".bash_history")
        with open(path, "w") as f:
            f.write("cmd1\ncmd2\n")
        svc = CleanerService()
        result = svc.run(["shell_history"], dry_run=False, create_backup=True)
        assert result.ok
        # Backup should exist
        assert len(backup_service.list_backups()) >= 1

    def test_unknown_target_returns_empty(self, tmp_home):
        svc = CleanerService()
        result = svc.run(["nonexistent_target"], dry_run=False)
        assert result.ok
        assert result.records == []