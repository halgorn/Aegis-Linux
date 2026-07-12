"""Tests for the per-scanner CLI."""
from __future__ import annotations

import json
import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "aegis", "scan", *args],
        capture_output=True, text=True, timeout=60,
        cwd="/home/bruno/Documents/GitHub/Aegis-Linux",
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
    )


def test_scan_help_lists_categories():
    r = subprocess.run(
        [sys.executable, "-m", "aegis", "scan", "--help"],
        capture_output=True, text=True,
        cwd="/home/bruno/Documents/GitHub/Aegis-Linux",
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0
    assert "health" in r.stdout
    assert "disks" in r.stdout
    assert "network" in r.stdout


def test_scan_health_outputs_json():
    r = _run("health")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "score" in data
    assert "issues" in data
    assert isinstance(data["score"], int)


def test_scan_disks_outputs_json():
    r = _run("disks")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "filesystems" in data
    assert isinstance(data["filesystems"], list)


def test_scan_network_outputs_json():
    r = _run("network")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "interfaces" in data
    assert "listening" in data


def test_scan_performance_outputs_json():
    r = _run("performance")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert isinstance(data, list)
    assert len(data) > 0
    assert "pid" in data[0]


def test_scan_unknown_category_fails():
    r = _run("does_not_exist")
    assert r.returncode == 2
    assert "invalid choice" in r.stderr.lower()


def test_to_jsonable_handles_dataclass_datetime_enum():
    from dataclasses import dataclass
    from datetime import datetime
    from enum import Enum
    from aegis.core.scanners import _to_jsonable

    class Color(Enum):
        RED = "red"

    @dataclass
    class Item:
        name: str
        when: datetime
        color: Color

    out = _to_jsonable(Item(name="x", when=datetime(2024, 1, 2, 3, 4, 5),
                            color=Color.RED))
    assert out == {"name": "x", "when": "2024-01-02T03:04:05", "color": "red"}