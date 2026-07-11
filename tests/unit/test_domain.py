"""Unit tests for the domain layer."""

from __future__ import annotations

import pytest

from aegis.domain.cleaner import (
    CleanCategory,
    CleanKind,
    CleanPlan,
    CleanRecord,
    CleanResult,
    CleanTarget,
    DuplicateGroup,
    LargeFile,
)
from aegis.domain.health import HealthIssue, HealthReport, Severity
from aegis.domain.packages import Package, PkgManager
from aegis.domain.system import CpuSample, MemorySample


class TestCleanTarget:
    def test_valid_target(self):
        t = CleanTarget(
            id="x", label="X", description="d",
            category=CleanCategory.SYSTEM,
            kind=CleanKind.DELETE_CONTENTS,
            paths=("/tmp/a",),
        )
        assert t.id == "x"
        assert t.paths == ("/tmp/a",)

    def test_missing_id_raises(self):
        with pytest.raises(ValueError):
            CleanTarget(id="", label="x", description="d",
                        category=CleanCategory.SYSTEM,
                        kind=CleanKind.DELETE_CONTENTS, paths=("/x",))

    def test_exec_needs_command(self):
        with pytest.raises(ValueError):
            CleanTarget(id="x", label="X", description="d",
                        category=CleanCategory.SYSTEM,
                        kind=CleanKind.EXEC, paths=())


class TestCleanPlan:
    def test_total_bytes(self):
        t = CleanTarget(
            id="x", label="X", description="d",
            category=CleanCategory.SYSTEM,
            kind=CleanKind.DELETE_CONTENTS,
            paths=("/x",),
            estimated_size=1024,
        )
        plan = CleanPlan(targets=[t])
        assert plan.total_estimated_bytes == 1024

    def test_by_category(self):
        t1 = CleanTarget(id="x", label="X", description="d",
                         category=CleanCategory.SYSTEM,
                         kind=CleanKind.DELETE_CONTENTS, paths=("/x",))
        t2 = CleanTarget(id="y", label="Y", description="d",
                         category=CleanCategory.BROWSER,
                         kind=CleanKind.DELETE_CONTENTS, paths=("/y",))
        groups = CleanPlan(targets=[t1, t2]).by_category()
        assert CleanCategory.SYSTEM in groups
        assert CleanCategory.BROWSER in groups
        assert len(groups[CleanCategory.SYSTEM]) == 1


class TestCleanResult:
    def test_aggregates(self):
        rec1 = CleanRecord(target_id="a", label="A",
                            bytes_freed=1024, files_removed=2,
                            started_at=None, finished_at=None, ok=True)
        rec2 = CleanRecord(target_id="b", label="B",
                            bytes_freed=2048, files_removed=3,
                            started_at=None, finished_at=None, ok=True)
        r = CleanResult(records=[rec1, rec2])
        assert r.bytes_freed == 3072
        assert r.files_removed == 5
        assert r.ok

    def test_failure_marks_not_ok(self):
        rec = CleanRecord(target_id="x", label="X",
                          bytes_freed=0, files_removed=0,
                          started_at=None, finished_at=None,
                          ok=False, error="boom")
        r = CleanResult(records=[rec])
        assert not r.ok
        assert "boom" in r.to_text()


class TestHealthReport:
    def test_starts_at_100(self):
        r = HealthReport()
        assert r.score == 100
        assert r.grade == "A"

    def test_add_deducts(self):
        r = HealthReport()
        r.add(HealthIssue(code="x", title="X", detail="d",
                          severity=Severity.HIGH))
        assert r.score == 85  # 100 - 5*3
        assert r.grade == "B"
        assert len(r.issues) == 1

    def test_grade_F(self):
        r = HealthReport()
        for i in range(12):
            r.add(HealthIssue(code=f"x{i}", title="X", detail="d",
                              severity=Severity.HIGH))
        assert r.grade == "F"

    def test_merge(self):
        a = HealthReport(score=80)
        a.add(HealthIssue(code="a", title="A", detail="d",
                          severity=Severity.LOW))
        b = HealthReport(score=70)
        b.add(HealthIssue(code="b", title="B", detail="d",
                          severity=Severity.HIGH))
        a.merge(b)
        # min wins (70); further deductions applied from b's own additions
        assert a.score == 55  # 70 - 5*3 (HIGH deduction)
        assert len(a.issues) == 2


class TestMemorySample:
    def test_used_pct(self):
        m = MemorySample(total=1000, free=200, buffers=100,
                         cached=100, swap_total=500, swap_free=250)
        assert m.used == 600
        assert abs(m.used_pct - 0.6) < 1e-9
        assert m.swap_used == 250
        assert abs(m.swap_used_pct - 0.5) < 1e-9


class TestCpuSample:
    def test_label(self):
        s = CpuSample(per_core_pct=(10, 20, 30), avg_pct=20.0,
                      freq_mhz=2400.0, temp_c=45.0, governor="schedutil",
                      cores=3)
        assert s.load_label == "20%"
        assert s.cores == 3


class TestPackage:
    def test_basic(self):
        p = Package(manager=PkgManager.APT, name="vim", version="9.0",
                    installed=True)
        assert p.manager is PkgManager.APT
        assert p.installed


class TestDuplicateGroup:
    def test_savings(self):
        g = DuplicateGroup(hash="abc", paths=("/a", "/b", "/c"), size=100)
        assert g.savings == 200  # 2 extra copies


class TestLargeFile:
    def test_basic(self):
        from datetime import datetime
        lf = LargeFile(path="/x", size=10, mtime=datetime.utcnow())
        assert lf.size == 10