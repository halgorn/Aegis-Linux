"""Shared Qt application for GUI tests — one QApplication per session."""
from __future__ import annotations

import os
import sys

import pytest

# Force offscreen platform early so no display is needed.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """Single QApplication for the whole test session."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL, True)
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    # Don't quit — other fixtures might still need it.
