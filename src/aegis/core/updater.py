"""Check for a newer version on GitHub.

Tiny stdlib-only implementation: GET ``repos/{owner}/{repo}/releases/latest``
through ``urllib.request`` (no extra dep), compare the tag_name against
the running version. Cached on disk for 24 hours so we don't hammer
the API.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from aegis.core.paths import xdg_cache_dir

_log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
DEFAULT_REPO = "halgorn/Aegis-Linux"
CACHE_FILENAME = "update_check.json"
CACHE_TTL_S = 24 * 3600
HTTP_TIMEOUT_S = 5


@dataclass(slots=True, frozen=True)
class UpdateInfo:
    current: str
    latest: str | None
    has_update: bool
    url: str | None = None
    checked_at: float = 0.0
    error: str = ""

    def to_text(self) -> str:
        if self.error:
            return f"Update check failed: {self.error}"
        if not self.has_update or not self.latest:
            return f"Aegis {self.current} is up to date."
        return f"A new version of Aegis is available: {self.latest} (you have {self.current}). See {self.url or 'the releases page'}."


def _parse_version(s: str) -> tuple[int, ...]:
    """``"v1.2.3"`` -> ``(1, 2, 3)``. Bad strings -> ``()``."""
    s = s.strip().lstrip("v").split("-")[0].split("+")[0]
    out: list[int] = []
    for chunk in s.split("."):
        try:
            out.append(int(chunk))
        except ValueError:
            return ()
    return tuple(out)


def _is_newer(latest: str, current: str) -> bool:
    lp, cp = _parse_version(latest), _parse_version(current)
    if not lp or not cp:
        return False
    return lp > cp


def _cache_path() -> Path:
    return xdg_cache_dir() / CACHE_FILENAME


def _read_cache() -> dict | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(raw.get("checked_at", 0)) > CACHE_TTL_S:
        return None
    return raw


def _write_cache(data: dict) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(data))
    except OSError as e:  # noqa: BLE001
        _log.debug("update cache write failed: %s", e)


def check_for_update(*, current: str, repo: str = DEFAULT_REPO,
                    force: bool = False) -> UpdateInfo:
    """Return the latest version if newer than ``current``.

    Skips the network entirely if a cached result less than
    :data:`CACHE_TTL_S` old exists. ``force=True`` bypasses the cache.
    """
    if not force:
        cached = _read_cache()
        if cached is not None:
            latest = cached.get("latest")
            url = cached.get("url")
            return UpdateInfo(
                current=current,
                latest=latest,
                has_update=_is_newer(latest or "", current),
                url=url,
                checked_at=float(cached.get("checked_at", 0)),
            )

    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
        latest = data.get("tag_name") or data.get("name") or ""
        html_url = data.get("html_url")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError) as e:
        _log.debug("update check failed: %s", e)
        return UpdateInfo(current=current, latest=None, has_update=False,
                          error=str(e))

    payload = {"latest": latest, "url": html_url, "checked_at": time.time()}
    _write_cache(payload)
    return UpdateInfo(
        current=current,
        latest=latest or None,
        has_update=_is_newer(latest, current),
        url=html_url,
        checked_at=payload["checked_at"],
    )