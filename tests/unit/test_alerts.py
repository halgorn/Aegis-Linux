"""Tests for the alert watcher."""
from __future__ import annotations

from dataclasses import dataclass

from aegis.services.alerts import AlertThresholds, AlertWatcher


@dataclass
class _FakeSample:
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    swap_pct: float = 0.0
    disk_used_pct: float = 0.0
    gpu_temp: float | None = None
    rx_kbps: float = 0.0
    tx_kbps: float = 0.0


def test_no_alert_when_under_threshold():
    posted: list = []
    w = AlertWatcher(AlertThresholds(), lambda m, k: posted.append((m, k)))
    w.check(_FakeSample(mem_pct=0.50, disk_used_pct=50.0))
    assert posted == []


def test_ram_alert_fires_once():
    posted: list = []
    w = AlertWatcher(AlertThresholds(), lambda m, k: posted.append((m, k)))
    s = _FakeSample(mem_pct=0.90)
    w.check(s)
    w.check(s)  # second time, already fired
    assert len(posted) == 1
    assert "RAM" in posted[0][0]


def test_disk_alert_fires_once():
    posted: list = []
    w = AlertWatcher(AlertThresholds(), lambda m, k: posted.append((m, k)))
    s = _FakeSample(disk_used_pct=95.0)
    w.check(s)
    w.check(s)
    assert len(posted) == 1
    assert "Disk" in posted[0][0]


def test_swap_alert_fires_once():
    posted: list = []
    w = AlertWatcher(AlertThresholds(), lambda m, k: posted.append((m, k)))
    s = _FakeSample(swap_pct=0.80)
    w.check(s)
    w.check(s)
    assert len(posted) == 1
    assert "Swap" in posted[0][0]


def test_gpu_temp_alert_fires_once():
    posted: list = []
    w = AlertWatcher(AlertThresholds(), lambda m, k: posted.append((m, k)))
    s = _FakeSample(gpu_temp=85.0)
    w.check(s)
    w.check(s)
    assert len(posted) == 1
    assert "GPU" in posted[0][0]


def test_reset_allows_firing_again():
    posted: list = []
    w = AlertWatcher(AlertThresholds(), lambda m, k: posted.append((m, k)))
    w.check(_FakeSample(mem_pct=0.95))
    assert len(posted) == 1
    w.reset()
    w.check(_FakeSample(mem_pct=0.95))
    assert len(posted) == 2


def test_missing_field_does_not_crash():
    posted: list = []
    w = AlertWatcher(AlertThresholds(), lambda m, k: posted.append((m, k)))
    # No gpu_temp at all (None)
    s = _FakeSample(mem_pct=0.95)
    s.gpu_temp = None
    w.check(s)
    assert len(posted) == 1
    assert "RAM" in posted[0][0]


def test_zero_threshold_disables_alert():
    posted: list = []
    thr = AlertThresholds(ram_pct=0.0, disk_pct=0.0, cpu_temp_c=0.0, swap_pct=0.0)
    w = AlertWatcher(thr, lambda m, k: posted.append((m, k)))
    w.check(_FakeSample(mem_pct=0.99, disk_used_pct=99.0, swap_pct=0.99, gpu_temp=99.0))
    assert posted == []


def test_from_config_returns_defaults():
    from aegis.core.config import Config
    thr = AlertThresholds.from_config(Config())
    assert thr.ram_pct == 0.85
    assert thr.disk_pct == 0.90
    assert thr.cpu_temp_c == 80.0
    assert thr.swap_pct == 0.50