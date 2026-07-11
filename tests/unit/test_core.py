"""Unit tests for the core infrastructure."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.core.config import Config
from aegis.core.logging import setup_logging, get_logger
from aegis.core.paths import (
    config_file, ensure_dirs, history_db, is_root, xdg_cache_dir,
    xdg_config_dir, xdg_data_dir, xdg_log_dir, plugin_dir,
)


class TestConfig:
    def test_defaults(self, tmp_home):
        cfg = Config.load()
        assert cfg.theme == "dark"
        assert cfg.accent == "blue"
        assert cfg.create_backup_before_clean is True

    def test_roundtrip(self, tmp_home):
        cfg = Config.load()
        cfg.theme = "light"
        cfg.accent = "mauve"
        cfg.backup_retention_days = 7
        cfg.save()
        cfg2 = Config.load()
        assert cfg2.theme == "light"
        assert cfg2.accent == "mauve"
        assert cfg2.backup_retention_days == 7

    def test_atomic_save_no_partial(self, tmp_home, monkeypatch):
        cfg = Config.load()
        cfg.theme = "light"
        cfg.save()
        # Now simulate crash during a *second* save: original file must survive
        cfg.theme = "shouldnotappear"
        # Patch os.fdopen to raise when used on our temp file.
        import os as _os
        real_fdopen = _os.fdopen

        def boom(fd, *args, **kw):
            import os as _o
            try:
                path = _o.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                path = ""
            if ".aegis-cfg-" in path:
                raise OSError("disk full mid-write")
            return real_fdopen(fd, *args, **kw)

        monkeypatch.setattr("aegis.core.config.os.fdopen", boom)
        with pytest.raises(Exception):
            cfg.save()
        monkeypatch.undo()
        cfg2 = Config.load()
        assert cfg2.theme == "light"  # original preserved

    def test_extra_keys_preserved(self, tmp_home):
        cfg = Config.load()
        cfg.set_extra("custom_plugin_x", {"foo": "bar"})
        cfg.save()
        cfg2 = Config.load()
        assert cfg2.get("custom_plugin_x") == {"foo": "bar"}

    def test_atomic_write_uses_rename(self, tmp_home):
        cfg = Config.load()
        cfg.theme = "dark"
        cfg.save()
        # Should not have leftover tmp files
        files = list(Path(xdg_config_dir()).iterdir())
        assert any(f.name == "config.json" for f in files)
        assert not any(f.name.startswith(".aegis-cfg-") for f in files)


class TestPaths:
    def test_xdg_under_home(self, tmp_home):
        # All XDG paths should fall under HOME
        for d in (xdg_config_dir(), xdg_data_dir(),
                  xdg_cache_dir(), xdg_log_dir()):
            assert str(d).startswith(tmp_home)

    def test_ensure_dirs_idempotent(self, tmp_home):
        ensure_dirs()
        ensure_dirs()  # second call shouldn't fail
        assert xdg_config_dir().is_dir()
        assert xdg_data_dir().is_dir()
        assert xdg_cache_dir().is_dir()
        assert xdg_log_dir().is_dir()
        assert plugin_dir().is_dir()

    def test_default_files(self, tmp_home):
        # After ensure_dirs, sub-paths still need explicit creation
        assert config_file().parent == xdg_config_dir()
        assert history_db().parent == xdg_data_dir()

    def test_is_root(self):
        # Just check it returns a bool without crashing
        assert isinstance(is_root(), bool)


class TestLogging:
    def test_setup_idempotent(self, tmp_home):
        l1 = setup_logging("INFO")
        l2 = setup_logging("DEBUG")
        # Same logger instance, level changed
        assert l1 is l2
        assert l2.level == 10  # DEBUG

    def test_get_logger_child(self):
        setup_logging("INFO")
        l = get_logger("foo.bar")
        assert l.name == "aegis.foo.bar"


class TestCleanerRules:
    def test_all_targets_resolve(self, tmp_home):
        from aegis.rules.cleaner_rules import all_targets, target_by_id
        targets = all_targets()
        assert len(targets) > 10
        for t in targets:
            assert t.id
            assert t.label
            assert target_by_id(t.id) is t

    def test_by_category_groups(self, tmp_home):
        from aegis.rules.cleaner_rules import by_category
        from aegis.domain.cleaner import CleanCategory
        cats = by_category()
        assert CleanCategory.SYSTEM in cats
        assert CleanCategory.BROWSER in cats
        assert CleanCategory.PACKAGE_MGR in cats

    def test_reversible_flag_set(self, tmp_home):
        from aegis.rules.cleaner_rules import target_by_id
        hist = target_by_id("shell_history")
        assert hist.reversible is True

    def test_root_flag_for_sudo_targets(self, tmp_home):
        from aegis.rules.cleaner_rules import target_by_id
        apt = target_by_id("apt_cache")
        journal = target_by_id("journal")
        pip = target_by_id("pip_cache")
        assert apt.needs_root is True
        assert journal.needs_root is True
        assert pip.needs_root is False