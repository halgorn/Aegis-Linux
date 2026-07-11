"""Shared pytest fixtures."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture()
def tmp_home(monkeypatch) -> Iterator[str]:
    """Replace $HOME with a fresh empty temp dir."""
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("HOME", d)
        # Invalidate the cached clean-target list so paths use the new HOME.
        from aegis.rules import cleaner_rules
        cleaner_rules._reset_cache()
        yield d


@pytest.fixture()
def tmp_workdir() -> Iterator[str]:
    """Yield a fresh temp dir for files / trees."""
    with tempfile.TemporaryDirectory() as d:
        yield d