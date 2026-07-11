"""Browser collectors — cookie/cache inventory per browser."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from aegis.core.logging import get_logger

_log = get_logger("collectors.browser")

_HOME = os.path.expanduser("~")


# ── registry ────────────────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class Browser:
    id: str
    label: str
    base: str                       # path containing profiles
    profile_pattern: str            # glob relative to base
    cookie_db: str                  # filename inside each profile
    cookie_table: str
    is_firefox_like: bool


_BROWSERS: tuple[Browser, ...] = (
    Browser("firefox", "Firefox",
            f"{_HOME}/.mozilla/firefox", "*", "cookies.sqlite",
            "moz_cookies", True),
    Browser("chrome", "Google Chrome",
            f"{_HOME}/.config/google-chrome", "*", "Cookies",
            "cookies", False),
    Browser("chromium", "Chromium",
            f"{_HOME}/.config/chromium", "*", "Cookies",
            "cookies", False),
    Browser("brave", "Brave",
            f"{_HOME}/.config/BraveSoftware/Brave-Browser", "*", "Cookies",
            "cookies", False),
    Browser("edge", "Microsoft Edge",
            f"{_HOME}/.config/microsoft-edge", "*", "Cookies",
            "cookies", False),
    Browser("opera", "Opera",
            f"{_HOME}/.config/opera", "*", "Cookies",
            "cookies", False),
    Browser("vivaldi", "Vivaldi",
            f"{_HOME}/.config/vivaldi", "*", "Cookies",
            "cookies", False),
)


def all_browsers() -> tuple[Browser, ...]:
    """Return only the browsers whose base directory exists."""
    return tuple(b for b in _BROWSERS if os.path.isdir(b.base))


# ── profile / cookie iteration ──────────────────────────────────────────────

def iter_cookie_dbs(browser: Browser) -> Iterator[tuple[str, str]]:
    """Yield ``(db_path, table)`` for every cookie DB in ``browser``."""
    base = Path(browser.base)
    if not base.is_dir():
        return
    for profile in base.glob(browser.profile_pattern):
        if not profile.is_dir():
            continue
        db = profile / browser.cookie_db
        if db.is_file():
            yield str(db), browser.cookie_table


# ── cookie count / wipe ─────────────────────────────────────────────────────

def count_cookies(browser: Browser) -> int:
    n = 0
    for db, table in iter_cookie_dbs(browser):
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
                n += int(cur.fetchone()[0])
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            _log.debug("count_cookies(%s): %s", db, exc)
    return n


def clear_cookies(browser: Browser) -> tuple[int, str]:
    """Delete every cookie from every profile. Returns (rows, error)."""
    total = 0
    errs: list[str] = []
    for db, table in iter_cookie_dbs(browser):
        try:
            with sqlite3.connect(db) as conn:
                cur = conn.execute(f"DELETE FROM {table}")
                total += cur.rowcount
                conn.commit()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            errs.append(str(exc))
    return total, "; ".join(errs)


# ── cache directory helpers (for cleaner rules) ────────────────────────────

def cache_dirs() -> tuple[str, ...]:
    """Return every browser cache directory that exists."""
    out: list[str] = []
    for b in _BROWSERS:
        if b.is_firefox_like:
            # ~/.mozilla/firefox/<profile>/cache/*
            base = Path(b.base)
            if base.is_dir():
                for profile in base.iterdir():
                    cache = profile / "cache2"
                    if cache.is_dir():
                        out.append(str(cache))
        else:
            # ~/.config/<browser>/Default/Cache
            base = Path(b.base)
            if base.is_dir():
                for profile in base.iterdir():
                    if not profile.is_dir():
                        continue
                    cache = profile / "Cache"
                    if cache.is_dir():
                        out.append(str(cache))
                    storage = profile / "Storage"
                    if storage.is_dir():
                        out.append(str(storage))
    return tuple(out)