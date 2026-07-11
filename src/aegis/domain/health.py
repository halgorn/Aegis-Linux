"""Domain model — system health scoring.

A :class:`HealthScore` is a number in 0–100 with a list of
:class:`HealthIssue` explaining the deduction. Issues are sorted by
severity, so the UI can show the worst ones first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class Severity(IntEnum):
    """How serious a health / security issue is."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(slots=True, frozen=True)
class HealthIssue:
    """One deductable from the health score."""

    code: str                 # stable id, e.g. "disk.full"
    title: str
    detail: str
    severity: Severity
    suggestion: str = ""
    data: dict = field(default_factory=dict)


@dataclass(slots=True)
class HealthReport:
    """Composite health snapshot."""

    score: int = 100
    issues: list[HealthIssue] = field(default_factory=list)
    taken_at: datetime = field(default_factory=datetime.utcnow)

    # --- builders -------------------------------------------------------

    def add(self, issue: HealthIssue) -> None:
        self.issues.append(issue)
        self.score = max(0, self.score - issue.severity * 5)
        self.issues.sort(key=lambda i: -i.severity)

    def merge(self, other: "HealthReport") -> None:
        self.issues.extend(other.issues)
        self.score = min(self.score, other.score)
        self.issues.sort(key=lambda i: -i.severity)

    # --- presentation ---------------------------------------------------

    @property
    def grade(self) -> str:
        if self.score >= 90: return "A"
        if self.score >= 80: return "B"
        if self.score >= 70: return "C"
        if self.score >= 50: return "D"
        return "F"

    @property
    def worst(self) -> list[HealthIssue]:
        return [i for i in self.issues if i.severity >= Severity.MEDIUM]

    def to_text(self) -> str:
        lines = [f"Health score: {self.score}/100  (grade {self.grade})", ""]
        if not self.issues:
            lines.append("No issues detected.")
            return "\n".join(lines)
        for i in self.issues:
            lines.append(
                f"  [{i.severity.label:>8}] {i.title}\n"
                f"             {i.detail}"
            )
            if i.suggestion:
                lines.append(f"             → {i.suggestion}")
        return "\n".join(lines)