"""Tests for simple-mode navigation."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def qt_app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_simple_mode_hides_advanced_pages(qt_app):
    from aegis.core.config import Config
    from aegis.ui.app_qt import MainWindow, _NAV_ITEMS, _SIMPLE_NAV_KEYS
    cfg = Config()
    cfg.simple_mode = True
    win = MainWindow(cfg)
    visible_keys = {it.key for it in win.sidebar._items}
    assert visible_keys == _SIMPLE_NAV_KEYS
    assert "monitor" not in visible_keys
    assert "drivers" not in visible_keys
    assert len(visible_keys) == 3


def test_advanced_mode_shows_all(qt_app):
    from aegis.core.config import Config
    from aegis.ui.app_qt import MainWindow, _NAV_ITEMS
    cfg = Config()
    cfg.simple_mode = False
    win = MainWindow(cfg)
    assert len(win.sidebar._items) == len(_NAV_ITEMS)


def test_toggle_simple_mode_runtime(qt_app):
    from aegis.core.config import Config
    from aegis.ui.app_qt import MainWindow
    cfg = Config()
    cfg.simple_mode = False
    win = MainWindow(cfg)
    assert len(win.sidebar._items) == 14
    win.set_simple_mode(True)
    assert len(win.sidebar._items) == 3
    win.set_simple_mode(False)
    assert len(win.sidebar._items) == 14