"""Filesystem collectors — hashing, large files, duplicate detection,
file-type classification. All walk the FS in-process (no ``du`` /
``find`` subprocess) and honour a cancel event.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run
from aegis.domain.cleaner import DuplicateGroup, LargeFile

_log = get_logger("collectors.filesystem")

ProgressCb = Callable[[int, int, str], None]   # (done, total, current_path)


# ── generic walker ──────────────────────────────────────────────────────────

def iter_files(root: str | os.PathLike,
               *,
               skip_names: frozenset[str] = frozenset(),
               skip_prefixes: tuple[str, ...] = (".",),
               max_depth: int | None = None,
               cancel: threading.Event | None = None,
               follow: bool = False,
               ) -> Iterator[str]:
    """Yield regular file paths under ``root``.

    * Prunes any dir whose name is in ``skip_names`` (e.g. ``node_modules``).
    * Prunes any dir starting with one of ``skip_prefixes`` (default:
      dotfiles).
    * Honours ``cancel`` between file emissions.
    """
    base = Path(root)
    if not base.exists():
        return
    for dirpath, dirnames, filenames in os.walk(base, followlinks=follow):
        if cancel is not None and cancel.is_set():
            return
        if max_depth is not None:
            depth = len(Path(dirpath).relative_to(base).parts)
            if depth >= max_depth:
                dirnames.clear()
        # in-place prune
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_names
            and not any(d.startswith(p) for p in skip_prefixes)
        ]
        for fname in filenames:
            fp = os.path.join(dirpath, fname)
            if cancel is not None and cancel.is_set():
                return
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            if os.path.islink(fp):
                continue
            if not os.path.isfile(fp):
                continue
            yield fp


# ── size ────────────────────────────────────────────────────────────────────

def file_size(path: str) -> int:
    try:
        return os.lstat(path).st_size
    except OSError:
        return 0


def total_size(paths: Iterable[str]) -> int:
    return sum(file_size(p) for p in paths)


# ── hashing ─────────────────────────────────────────────────────────────────

_HASH_CHUNK = 1 << 20      # 1 MiB
_HASH_FULL_THRESHOLD = 1 << 30  # 1 GiB — past this, do two-stage quick+full


def hash_file(path: str, algo: str = "sha256", *,
              quick: bool = False,
              cancel: threading.Event | None = None) -> str | None:
    """Hash a file.

    * ``quick=True`` → read only the first 1 MiB (good pre-filter for
      duplicate detection).
    * Returns ``None`` on read errors.
    * Honours ``cancel`` between chunks.
    """
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as fp:
            read = fp.read
            if quick:
                data = read(_HASH_CHUNK)
                if not data:
                    return h.hexdigest()
                h.update(data)
                return h.hexdigest()
            while True:
                if cancel is not None and cancel.is_set():
                    return None
                chunk = read(_HASH_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
    except (OSError, PermissionError) as exc:
        _log.debug("hash_file(%s) failed: %s", path, exc)
        return None
    return h.hexdigest()


# ── large files ─────────────────────────────────────────────────────────────

def find_large_files(root: str,
                     min_bytes: int,
                     limit: int = 100,
                     cancel: threading.Event | None = None,
                     on_progress: ProgressCb | None = None,
                     ) -> tuple[LargeFile, ...]:
    """Top-``limit`` files >= ``min_bytes`` under ``root``."""
    bucket: list[tuple[int, str, float]] = []
    done = 0
    total_hint = 0
    for fp in iter_files(root, cancel=cancel):
        sz = file_size(fp)
        done += 1
        if sz >= min_bytes:
            try:
                mtime = os.stat(fp).st_mtime
            except OSError:
                mtime = 0.0
            bucket.append((sz, fp, mtime))
            if len(bucket) > limit * 4:
                bucket.sort(reverse=True)
                bucket = bucket[:limit]
        if on_progress and done % 256 == 0:
            on_progress(done, total_hint or done, fp)

    bucket.sort(reverse=True)
    out: list[LargeFile] = []
    for sz, fp, mtime in bucket[:limit]:
        out.append(LargeFile(
            path=fp,
            size=sz,
            mtime=datetime.fromtimestamp(mtime) if mtime else datetime.utcnow(),
        ))
    return tuple(out)


# ── duplicate detection ─────────────────────────────────────────────────────

@dataclass(slots=True)
class _SizeBucket:
    size: int
    paths: list[str]


def find_duplicates(root: str,
                    min_bytes: int = 1024,
                    *,
                    quick_hash: bool = True,
                    cancel: threading.Event | None = None,
                    on_progress: ProgressCb | None = None,
                    ) -> tuple[DuplicateGroup, ...]:
    """Two-stage duplicate detector: size-bucket, then (quick) hash,
    then full hash. Emits progress for each stage.

    For very large files (>1 GiB) the full-hash stage is skipped
    because of I/O cost; we trust the quick hash.
    """
    by_size: dict[int, list[str]] = defaultdict(list)
    done = 0
    for fp in iter_files(root, cancel=cancel):
        sz = file_size(fp)
        done += 1
        if sz >= min_bytes:
            by_size[sz].append(fp)
        if on_progress and done % 512 == 0:
            on_progress(done, 0, fp)

    # stage 2: quick hash on candidates with > 1 file
    by_quick: dict[str, list[str]] = defaultdict(list)
    candidates = [paths for paths in by_size.values() if len(paths) > 1]
    total = sum(len(p) for p in candidates)
    n = 0
    for paths in candidates:
        for fp in paths:
            if cancel is not None and cancel.is_set():
                return ()
            h = hash_file(fp, algo="md5", quick=True, cancel=cancel)
            if h is None:
                continue
            by_quick[h].append(fp)
            n += 1
            if on_progress and n % 32 == 0:
                on_progress(n, total, fp)

    # stage 3: full hash on > 1-file groups
    out: list[DuplicateGroup] = []
    for h, paths in by_quick.items():
        if len(paths) < 2:
            continue
        if cancel is not None and cancel.is_set():
            return ()
        full_buckets: dict[str, list[str]] = defaultdict(list)
        for fp in paths:
            if cancel is not None and cancel.is_set():
                return ()
            full = hash_file(fp, algo="sha256", quick=False, cancel=cancel)
            if full is None:
                continue
            full_buckets[full].append(fp)
        for full, ps in full_buckets.items():
            if len(ps) >= 2:
                out.append(DuplicateGroup(hash=full, paths=tuple(ps),
                                          size=file_size(ps[0])))

    out.sort(key=lambda g: g.savings, reverse=True)
    return tuple(out)


# ── broken symlinks ─────────────────────────────────────────────────────────

def find_broken_symlinks(root: str,
                         skip_names: frozenset[str] = frozenset(),
                         cancel: threading.Event | None = None,
                         ) -> tuple[str, ...]:
    out: list[str] = []
    base = Path(root)
    if not base.exists():
        return ()
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        if cancel is not None and cancel.is_set():
            return ()
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_names and not d.startswith(".")
        ]
        for name in list(dirnames) + filenames:
            fp = os.path.join(dirpath, name)
            if cancel is not None and cancel.is_set():
                return ()
            if os.path.islink(fp) and not os.path.exists(fp):
                out.append(fp)
    return tuple(out)


# ── file-type detection ─────────────────────────────────────────────────────

_TEXT_EXT = frozenset({
    ".txt", ".md", ".log", ".json", ".yaml", ".yml", ".toml",
    ".cfg", ".ini", ".conf", ".py", ".js", ".ts", ".rs", ".go",
    ".c", ".h", ".cpp", ".hpp", ".sh", ".bash", ".zsh",
})


def looks_like_text(path: str) -> bool:
    """Heuristic: extension or first 8 KiB has no NUL bytes."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _TEXT_EXT:
        return True
    try:
        with open(path, "rb") as fp:
            chunk = fp.read(8192)
    except OSError:
        return False
    return b"\x00" not in chunk