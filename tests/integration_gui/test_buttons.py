"""Regression test — every scan-style button in the Aegis GUI.

Loads the MainWindow, walks each page that has a scan button, clicks
it and verifies the visual feedback (label flips to busy, then resets)
plus that the underlying data actually changes. This is an integration
test, not a unit test — it imports PyQt6 and a virtual display so CI
needs \`QT_QPA_PLATFORM=offscreen\` and a working OpenGL stack."""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

_QT_OK = True
try:
    from aegis.ui.app_qt import MainWindow
    from aegis.core.config import Config
except Exception:  # noqa: BLE001
    _QT_OK = False

pytestmark = pytest.mark.skipif(
    not _QT_OK or os.environ.get("QT_QPA_PLATFORM") not in ("offscreen", None),
    reason="requires PyQt6 + offscreen Qt platform",
)




def _pump(app, seconds: float, predicate=None):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.05)
        if predicate and predicate():
            return True
    return predicate() if predicate else True


def test_main_window_renders_all_pages(qapp):
    win = MainWindow(Config.load())
    win.resize(1280, 780)
    win.show()
    _pump(qapp, 2.0)
    assert len(win._pages) == 14


def test_cleaner_scan_button_updates_total(qapp):
    win = MainWindow(Config.load()); win.resize(1280, 780); win.show()
    _pump(qapp, 1.0)
    win.show_page("cleaner")
    c = win._pages["cleaner"]
    assert c._table.rowCount() == 29
    assert len(c._checks) == 29
    c._btn_scan.click()
    ok = _pump(qapp, 8.0, lambda: c._total_lbl.text() not in ("…", "—"))
    assert ok, "cleaner total should leave the placeholder"
    assert c._total_lbl.text().endswith("GB") or "MB" in c._total_lbl.text()


def test_cleaner_clean_selected_dry_run(qapp):
    win = MainWindow(Config.load()); win.resize(1280, 780); win.show()
    _pump(qapp, 1.0)
    win.show_page("cleaner")
    c = win._pages["cleaner"]
    c._dryrun.setChecked(True)
    for tid in ("pip_cache", "npm_cache", "font_cache"):
        if tid in c._checks:
            c._checks[tid].setChecked(True)
    c._btn_clean.click()
    assert c._btn_clean.text() == "Cleaning…"
    assert not c._btn_clean.isEnabled()
    ok = _pump(qapp, 15.0,
               lambda: c._btn_clean.isEnabled()
               and c._btn_clean.text() == "Clean selected")
    assert ok


def test_health_run_scan_updates_score(qapp):
    win = MainWindow(Config.load()); win.resize(1280, 780); win.show()
    _pump(qapp, 1.0)
    win.show_page("health")
    h = win._pages["health"]
    _pump(qapp, 40.0,
          lambda: h._gauge._value > 0 and h._tbl.rowCount() > 0
          and h._btn_scan.text() == "Run scan")
    assert h._tbl.rowCount() > 0
    h._btn_scan.click()
    assert h._btn_scan.text() == "Run scan · …"
    ok = _pump(qapp, 40.0,
               lambda: h._btn_scan.text() == "Run scan" and h._tbl.rowCount() > 0)
    assert ok


def test_other_pages_populate_via_on_show(qapp):
    """Pages without explicit buttons still drive scans from on_show."""
    win = MainWindow(Config.load()); win.resize(1280, 780); win.show()
    _pump(qapp, 1.0)

    expectations = {
        "network": lambda p: p._ifaces.rowCount() > 0 or p._ports.rowCount() > 0,
        "disks":   lambda p: p._tbl.rowCount() > 0,
        "drivers": lambda p: p._tbl.rowCount() > 0,
        "startup": lambda p: p._tbl.rowCount() > 0,
        "security": lambda p: p._tbl.rowCount() > 0,
        "logs":    lambda p: bool(p._view.toPlainText()),
        "performance": lambda p: p._tbl.rowCount() > 0,
    }
    for pg, pred in expectations.items():
        win.show_page(pg)
        page = win._pages[pg]
        ok = _pump(qapp, 8.0, lambda p=page: pred(p))
        assert ok, f"page {pg} failed to populate"


def test_restore_refresh_does_not_crash(qapp):
    win = MainWindow(Config.load()); win.resize(1280, 780); win.show()
    _pump(qapp, 1.0)
    win.show_page("restore")
    r = win._pages["restore"]
    r._btn_refresh.click()
    _pump(qapp, 1.0)
    # No backups on a fresh system — but the click must not throw.
