"""Tests for the i18n module."""
from __future__ import annotations

import os

from aegis.core import i18n


def teardown_function(_):
    i18n.set_locale("en")
    os.environ.pop("AEGIS_LANG", None)


def test_default_locale_is_english():
    i18n.set_locale("en")
    assert i18n.tr("cleaner.title") == "Cleaner"


def test_set_locale_pt_br():
    i18n.set_locale("pt-BR")
    assert i18n.tr("cleaner.title") == "Limpeza"
    assert i18n.tr("nav.dashboard") == "Painel"


def test_format_kwargs():
    i18n.set_locale("pt-BR")
    msg = i18n.tr("cleaner.toast_clean_done", size="29 GB", n=12)
    assert msg == "Recuperado 29 GB em 12 itens."


def test_missing_key_returns_key():
    i18n.set_locale("en")
    assert i18n.tr("this.key.does.not.exist") == "this.key.does.not.exist"


def test_missing_key_falls_back_to_english():
    """A key in en but not pt-BR must fall back to en."""
    i18n.MESSAGES_PT_BR.pop("scan.failed", None)  # ensure absent
    i18n.set_locale("pt-BR")
    assert i18n.tr("scan.failed", name="health", err="boom") == "health failed: boom"


def test_env_override_wins():
    os.environ["AEGIS_LANG"] = "pt-BR"
    i18n.current_locale.cache_clear()
    assert i18n.current_locale() == "pt-BR"
    assert i18n.tr("cleaner.title") == "Limpeza"


def test_supported_locales_listed():
    codes = [code for code, _ in i18n.available_locales()]
    assert "en" in codes
    assert "pt-BR" in codes


def test_supported_attribute():
    assert "en" in i18n.SUPPORTED
    assert "pt-BR" in i18n.SUPPORTED