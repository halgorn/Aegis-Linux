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

    def to_dict(self) -> dict:
        """JSON-safe representation."""
        return {
            "score": self.score,
            "grade": self.grade,
            "taken_at": self.taken_at.isoformat(),
            "issues": [
                {
                    "code": i.code,
                    "title": i.title,
                    "detail": i.detail,
                    "severity": i.severity.label,
                    "severity_value": int(i.severity),
                    "suggestion": i.suggestion,
                    "data": dict(i.data) if i.data else {},
                }
                for i in self.issues
            ],
        }

    def to_html(self) -> str:
        """Standalone HTML report — printable, no JS, no external assets.

        The user can open this in a browser and Ctrl-P to PDF. We avoid
        a WeasyPrint/reportlab dependency; the HTML is small enough to
        hand-author.
        """
        sev_colors = {
            "low": "#4a90e2", "medium": "#f5a623",
            "high": "#e74c3c", "critical": "#8b0000",
        }
        rows: list[str] = []
        for i in self.issues:
            color = sev_colors.get(i.severity.label, "#888")
            rows.append(
                f"<tr><td><span style='color:{color};font-weight:600'>"
                f"[{i.severity.label.upper()}]</span></td>"
                f"<td><b>{_html_escape(i.title)}</b><br>"
                f"<small>{_html_escape(i.detail)}</small>"
                + (f"<br><i>→ {_html_escape(i.suggestion)}</i>" if i.suggestion else "")
                + "</td></tr>"
            )
        body = "".join(rows) or "<tr><td colspan=2><i>No issues detected.</i></td></tr>"
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Aegis Linux - Health Report</title>
<style>
body {{ font: 14px/1.5 -apple-system, system-ui, sans-serif;
       max-width: 800px; margin: 40px auto; padding: 0 20px; color: #222; }}
h1 {{ margin-bottom: 0; }}
.score {{ font-size: 48px; font-weight: 700; margin: 0; }}
.grade {{ display: inline-block; padding: 4px 12px; background: #4a90e2;
          color: #fff; border-radius: 4px; font-weight: 600; margin-left: 12px; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 24px; }}
td {{ padding: 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
@media print {{ body {{ margin: 0; }} }}
</style></head><body>
<h1>Aegis Linux - Health Report</h1>
<p class="score">{self.score}/100 <span class="grade">{self.grade}</span></p>
<p><small>Generated {_html_escape(self.taken_at.isoformat())}</small></p>
<table>{body}</table>
</body></html>"""


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))