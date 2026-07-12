"""Tests for the update checker."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest


def test_parse_version_basic():
    from aegis.core.updater import _parse_version
    assert _parse_version("v1.2.3") == (1, 2, 3)
    assert _parse_version("1.2.3") == (1, 2, 3)
    assert _parse_version("v0.1.0") == (0, 1, 0)
    assert _parse_version("v1.0.0-rc1") == (1, 0, 0)
    assert _parse_version("v1.0.0+local") == (1, 0, 0)
    assert _parse_version("not-a-version") == ()


def test_is_newer():
    from aegis.core.updater import _is_newer
    assert _is_newer("v1.2.3", "1.2.2") is True
    assert _is_newer("v1.2.4", "1.2.3") is True
    assert _is_newer("1.2.3", "1.2.3") is False
    assert _is_newer("1.2.3", "1.2.4") is False
    assert _is_newer("2.0.0", "1.9.9") is True
    assert _is_newer("v1.2.1", "1.2.0") is True
    assert _is_newer("garbage", "1.0.0") is False  # bad parse -> no update


def test_to_text_no_update():
    from aegis.core.updater import UpdateInfo
    u = UpdateInfo(current="1.0.0", latest=None, has_update=False)
    assert "up to date" in u.to_text()


def test_to_text_with_update():
    from aegis.core.updater import UpdateInfo
    u = UpdateInfo(current="1.0.0", latest="1.1.0", has_update=True,
                   url="https://github.com/halgorn/Aegis-Linux/releases/tag/v1.1.0")
    txt = u.to_text()
    assert "1.1.0" in txt
    assert "1.0.0" in txt


def test_to_text_with_error():
    from aegis.core.updater import UpdateInfo
    u = UpdateInfo(current="1.0.0", latest=None, has_update=False, error="timeout")
    assert "failed" in u.to_text()


def test_cache_roundtrip(tmp_home):
    """Cache write then read should return same payload if not expired."""
    from aegis.core import paths
    paths.xdg_cache_dir().mkdir(parents=True, exist_ok=True)
    from aegis.core.updater import _read_cache, _write_cache, _cache_path
    payload = {"latest": "v9.9.9", "url": "x", "checked_at": time.time()}
    _write_cache(payload)
    assert _read_cache()["latest"] == "v9.9.9"


def test_cache_expired(tmp_home):
    """Cache older than CACHE_TTL_S should return None."""
    from aegis.core.updater import _read_cache, _write_cache, _cache_path, CACHE_TTL_S
    _write_cache({"latest": "v9.9.9", "checked_at": time.time() - CACHE_TTL_S - 1})
    assert _read_cache() is None


def test_check_uses_cache(tmp_home, monkeypatch):
    """When a fresh cache exists, no network call is made."""
    from aegis.core import paths
    paths.xdg_cache_dir().mkdir(parents=True, exist_ok=True)
    from aegis.core.updater import _write_cache, check_for_update
    _write_cache({"latest": "v1.5.0", "url": "x", "checked_at": time.time()})
    with patch("aegis.core.updater.urllib.request.urlopen") as mock:
        info = check_for_update(current="1.0.0")
        mock.assert_not_called()
    assert info.has_update is True
    assert info.latest == "v1.5.0"


def test_check_force_calls_network(tmp_home, monkeypatch):
    """force=True bypasses cache and hits the network."""
    from aegis.core import paths
    paths.xdg_cache_dir().mkdir(parents=True, exist_ok=True)
    from aegis.core.updater import _write_cache, check_for_update
    _write_cache({"latest": "v1.5.0", "checked_at": time.time()})

    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({
        "tag_name": "v2.0.0", "html_url": "http://x",
    }).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("aegis.core.updater.urllib.request.urlopen",
               return_value=fake_resp):
        info = check_for_update(current="1.0.0", force=True)
    assert info.latest == "v2.0.0"
    assert info.has_update is True


def test_check_handles_network_error(tmp_home, monkeypatch):
    """A network error must return UpdateInfo with error set, not raise."""
    import urllib.error
    from aegis.core.updater import check_for_update
    with patch("aegis.core.updater.urllib.request.urlopen",
               side_effect=urllib.error.URLError("no internet")):
        info = check_for_update(current="1.0.0", force=True)
    assert info.has_update is False
    assert info.latest is None
    assert "no internet" in info.error