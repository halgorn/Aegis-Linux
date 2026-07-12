"""Tests for HealthReport serialisation (text/json/html)."""
from __future__ import annotations

import json

import pytest

from aegis.domain.health import HealthIssue, HealthReport, Severity


def _sample_report() -> HealthReport:
    r = HealthReport()
    r.add(HealthIssue(
        code="ram.pressure", title="RAM pressure",
        detail="Only 1 GB available", severity=Severity.HIGH,
        suggestion="Close some apps.",
    ))
    r.add(HealthIssue(
        code="kernel.old", title="Old kernel",
        detail="linux-image-6.8", severity=Severity.MEDIUM,
    ))
    return r


def test_to_text_basic():
    r = _sample_report()
    txt = r.to_text()
    assert "65" in txt or str(r.score) in txt
    assert "RAM pressure" in txt
    assert "Old kernel" in txt


def test_to_dict_roundtrip_json():
    r = _sample_report()
    d = r.to_dict()
    s = json.dumps(d)
    parsed = json.loads(s)
    assert parsed["score"] == r.score
    assert parsed["grade"] == r.grade
    assert len(parsed["issues"]) == 2
    assert parsed["issues"][0]["severity"] in ("high", "medium")
    assert "taken_at" in parsed


def test_to_dict_severity_value_is_int():
    r = _sample_report()
    d = r.to_dict()
    for issue in d["issues"]:
        assert isinstance(issue["severity_value"], int)


def test_to_html_escapes_special_chars():
    r = HealthReport()
    r.add(HealthIssue(
        code="xss", title="<script>alert(1)</script>",
        detail="\"quotes\" & ampersand",
        severity=Severity.LOW,
    ))
    html = r.to_html()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;quotes&quot;" in html
    assert "&amp; ampersand" in html


def test_to_html_contains_grade_and_score():
    r = _sample_report()
    html = r.to_html()
    assert str(r.score) in html
    assert r.grade in html
    assert "<!doctype html>" in html.lower()


def test_to_html_empty_report():
    r = HealthReport()
    html = r.to_html()
    assert "100" in html
    assert "A" in html
    assert "No issues" in html


def test_export_health_text():
    from aegis.core.scanners import export_health
    out = export_health(fmt="text")
    assert "Health score" in out


def test_export_health_json():
    from aegis.core.scanners import export_health
    out = export_health(fmt="json")
    data = json.loads(out)
    assert "score" in data and "issues" in data


def test_export_health_html():
    from aegis.core.scanners import export_health
    out = export_health(fmt="html")
    assert "<!doctype html>" in out.lower()
    assert "<table>" in out