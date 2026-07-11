"""Backward-compat shim.

The pages used to live in this single 1261-LOC file. They've been
split into ``pages/qt/`` (one file per page, ≤ 500 LOC each) and the
helpers into ``pages/qt/_helpers.py``. This module re-exports the
``build_pages`` factory so existing imports keep working.
"""
from aegis.ui.pages.qt import build_pages

__all__ = ["build_pages"]