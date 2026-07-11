"""Unit tests for the filesystem collector."""

from __future__ import annotations

import os
import threading

import pytest

from aegis.collectors.filesystem import (
    find_broken_symlinks,
    find_duplicates,
    find_large_files,
    hash_file,
    iter_files,
    looks_like_text,
)


def _make_tree(root, files: dict[str, int], *, symlinks: dict[str, str] | None = None):
    """Create a tree of files. ``files``: relative path -> size in bytes.

    If a value is a tuple ``(size, content)``, ``content`` is written
    verbatim instead of padding with ``"x" * size``.
    """
    symlinks = symlinks or {}
    for rel, spec in files.items():
        if isinstance(spec, tuple):
            size, content = spec
        else:
            size, content = spec, b"x" * spec
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p) or root, exist_ok=True)
        with open(p, "wb") as f:
            f.write(content)
    for rel, target in symlinks.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p) or root, exist_ok=True)
        if os.path.exists(p) or os.path.islink(p):
            os.remove(p)
        os.symlink(target, p)


class TestIterFiles:
    def test_basic_walk(self, tmp_workdir):
        _make_tree(tmp_workdir, {"a.txt": 5, "b/c.txt": 5, "b/d.txt": 10})
        files = sorted(iter_files(tmp_workdir))
        assert any(f.endswith("a.txt") for f in files)
        assert any(f.endswith("c.txt") for f in files)
        assert any(f.endswith("d.txt") for f in files)

    def test_skip_dotfiles(self, tmp_workdir):
        _make_tree(tmp_workdir, {"a.txt": 5, ".hidden.txt": 5})
        files = list(iter_files(tmp_workdir))
        assert any(f.endswith("a.txt") for f in files)
        assert not any(".hidden" in f for f in files)

    def test_skip_names(self, tmp_workdir):
        _make_tree(tmp_workdir, {"keep.txt": 5, "node_modules/junk.txt": 5})
        files = list(iter_files(tmp_workdir, skip_names=frozenset({"node_modules"})))
        assert any(f.endswith("keep.txt") for f in files)
        assert not any("node_modules" in f for f in files)

    def test_max_depth(self, tmp_workdir):
        _make_tree(tmp_workdir, {"a.txt": 1, "b/c/d/e.txt": 1})
        files = list(iter_files(tmp_workdir, max_depth=2))
        assert any(f.endswith("a.txt") for f in files)
        assert not any("e.txt" in f for f in files)

    def test_cancel_event(self, tmp_workdir):
        _make_tree(tmp_workdir, {f"f{i}.txt": 1 for i in range(20)})
        ev = threading.Event()
        ev.set()  # pre-cancelled
        files = list(iter_files(tmp_workdir, cancel=ev))
        assert files == []


class TestHashFile:
    def test_known_md5(self, tmp_workdir):
        p = os.path.join(tmp_workdir, "h.txt")
        with open(p, "wb") as f:
            f.write(b"hello world")
        # md5("hello world") = 5eb63bbbe01eeed093cb22bb8f5acdc3
        assert hash_file(p, "md5", quick=False) == "5eb63bbbe01eeed093cb22bb8f5acdc3"

    def test_quick_matches_full_small(self, tmp_workdir):
        p = os.path.join(tmp_workdir, "h.txt")
        with open(p, "wb") as f:
            f.write(b"x" * 100)
        assert hash_file(p, "md5", quick=True) == hash_file(p, "md5", quick=False)

    def test_nonexistent(self, tmp_workdir):
        assert hash_file(os.path.join(tmp_workdir, "missing.txt")) is None


class TestFindDuplicates:
    def test_basic_dup(self, tmp_workdir):
        content = b"A" * 50
        _make_tree(tmp_workdir, {
            "a.txt": (50, content),
            "b/copy1.txt": (50, content),
            "b/copy2.txt": (50, content),
            "b/different.txt": (10, b"B" * 10),
        })
        groups = find_duplicates(tmp_workdir, min_bytes=1)
        assert len(groups) == 1
        assert len(groups[0].paths) == 3  # 3 identical copies
        assert not any("different" in p for p in groups[0].paths)


class TestFindLargeFiles:
    def test_threshold(self, tmp_workdir):
        _make_tree(tmp_workdir, {"small.txt": 10, "big.bin": 5000})
        out = find_large_files(tmp_workdir, min_bytes=1000, limit=10)
        assert len(out) == 1
        assert out[0].size == 5000


class TestFindBrokenSymlinks:
    def test_finds_broken(self, tmp_workdir):
        _make_tree(tmp_workdir, {
            "good.txt": 5,
        })
        # Add a broken symlink manually
        link = os.path.join(tmp_workdir, "broken.lnk")
        os.symlink("/nonexistent_target_xyz", link)
        broken = find_broken_symlinks(tmp_workdir, limit=10)
        assert any("broken.lnk" in b for b in broken)


class TestLooksLikeText:
    def test_text(self, tmp_workdir):
        p = os.path.join(tmp_workdir, "t.txt")
        open(p, "w").write("plain text")
        assert looks_like_text(p)

    def test_binary(self, tmp_workdir):
        p = os.path.join(tmp_workdir, "b.bin")
        with open(p, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        assert not looks_like_text(p)