"""Tests for the first-run wizard."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_needs_wizard_when_first_run_incomplete(tmp_home):
    from aegis.core.config import Config
    from aegis.ui.wizard import needs_wizard
    cfg = Config()
    cfg.first_run_complete = False
    assert needs_wizard(cfg) is True


def test_skips_wizard_after_complete(tmp_home):
    from aegis.core.config import Config
    from aegis.ui.wizard import needs_wizard
    cfg = Config()
    cfg.first_run_complete = True
    assert needs_wizard(cfg) is False


def test_wizard_runs_and_writes_config(qt_app, tmp_home):
    """Drive the wizard through all 4 steps and verify it writes config."""
    from aegis.core.config import Config
    from aegis.ui.wizard import FirstRunWizard
    cfg = Config()
    wiz = FirstRunWizard(cfg)
    # step 0: language (en is default)
    wiz._stack.setCurrentIndex(0)
    # step 1: theme (dark is default)
    wiz._stack.setCurrentIndex(1)
    # step 2: mode (advanced is default - leave it)
    wiz._stack.setCurrentIndex(2)
    # step 3: telemetry (unchecked by default)
    wiz._stack.setCurrentIndex(3)
    # Now finish
    wiz._on_finish()
    assert cfg.first_run_complete is True
    assert cfg.theme == "dark"
    assert cfg.simple_mode is False
    assert cfg.enable_telemetry is False


def test_wizard_simple_mode_choice(qt_app, tmp_home):
    from aegis.core.config import Config
    from aegis.ui.wizard import FirstRunWizard
    cfg = Config()
    wiz = FirstRunWizard(cfg)
    wiz._stack.setCurrentIndex(2)
    # Find the "simple" radio and check it.
    from aegis.ui.wizard import _ModeStep
    step = wiz._steps[2]
    assert isinstance(step, _ModeStep)
    simple_btn = step._group.buttons()[1]  # second radio = simple
    simple_btn.setChecked(True)
    wiz._on_finish()
    assert cfg.simple_mode is True


def test_wizard_next_refreshes_translations(qt_app, tmp_home):
    """Regression: clicking Next on the language step must not crash.

    Bug: ``_refresh_translations()`` did ``step.children()[0].setText(...)``
    which is a QVBoxLayout (not a label). Stores the title key on each
    step instead and uses ``step.retranslate()``.
    """
    from aegis.core.config import Config
    from aegis.core import i18n
    from aegis.ui.wizard import FirstRunWizard
    cfg = Config()
    wiz = FirstRunWizard(cfg)
    i18n.set_locale("en")
    # Click Next on the language step — this used to crash.
    wiz._stack.setCurrentIndex(0)
    wiz._on_next()
    # Title on step 0 should now show the en translation (no-op, same).
    assert wiz._steps[0]._title_lbl.text() == i18n.tr("wizard.lang.title")
    # Now switch to pt-BR and confirm the title updates.
    i18n.set_locale("pt-BR")
    pt_step = wiz._steps[0]
    pt_step.retranslate()
    assert pt_step._title_lbl.text() == i18n.tr("wizard.lang.title", _locale=None) or \
           "Escolha" in pt_step._title_lbl.text()