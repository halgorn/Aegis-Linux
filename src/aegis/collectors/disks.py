"""Disk & mount collectors — ``df``, ``lsblk``, ``/proc/diskstats``."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

from aegis.core.logging import get_logger
from aegis.core.process import run
from aegis.domain.system import DiskIoSample, DiskMount

_log = get_logger("collectors.disks")

_SKIP_FS = frozenset({
    "tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs", "devpts",
    "cgroup", "cgroup2", "pstore", "securityfs", "debugfs", "hugetlbfs",
    "mqueue", "fusectl", "efivarfs", "bpf", "tracefs", "udev", "ramfs",
    "autofs", "nsfs", "fuse.gvfsd-fuse", "binfmt_misc", "configfs",
    "rpc_pipefs", "fuse.portal", "fuse.snapfuse",
})
_SKIP_MNT_PREFIXES = ("/proc", "/sys", "/dev", "/run/user", "/run/lock",
                       "/snap", "/boot/efi", "/var/lib/docker/overlay2")


def _parse_size(value: str) -> int:
    """Parse a df-style size like ``1234567`` into bytes."""
    try:
        return int(value)
    except ValueError:
        return 0


def read_mounts() -> tuple[DiskMount, ...]:
    """Return ``df -B1`` rows as :class:`DiskMount` objects."""
    r = run(["df", "-B1", "--output=source,target,size,used,avail,fstype"],
            timeout=15)
    if not r.ok:
        _log.debug("df failed: %s", r.stderr)
        return ()
    out: list[DiskMount] = []
    for i, line in enumerate(r.stdout.splitlines()):
        if i == 0:
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        device, mount, size, used, avail, fstype = parts[:6]
        if fstype in _SKIP_FS:
            continue
        if any(mount.startswith(p) for p in _SKIP_MNT_PREFIXES):
            continue
        out.append(DiskMount(
            device=device,
            mount=mount,
            fstype=fstype,
            size=_parse_size(size),
            used=_parse_size(used),
            avail=_parse_size(avail),
        ))
    return tuple(out)


def read_diskstats() -> dict[str, DiskIoSample]:
    """Return per-device cumulative I/O counters from ``/proc/diskstats``."""
    out: dict[str, DiskIoSample] = {}
    try:
        text = Path("/proc/diskstats").read_text()
    except OSError:
        return out
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            name = parts[2]
            reads_completed = int(parts[3])
            sectors_read = int(parts[5])
            writes_completed = int(parts[7])
            sectors_written = int(parts[9])
        except ValueError:
            continue
        out[name] = DiskIoSample(
            read_bytes=sectors_read * 512,
            write_bytes=sectors_written * 512,
            read_iops=reads_completed,
            write_iops=writes_completed,
        )
    return out


# ── lsblk (block device inventory) ──────────────────────────────────────────


def list_block_devices() -> tuple[dict, ...]:
    """Return ``lsblk -J`` rows as plain dicts (device, size, type, …)."""
    r = run(["lsblk", "-J", "-b", "-o",
             "NAME,TYPE,SIZE,ROTA,MODEL,SERIAL,TRAN,FSTYPE,MOUNTPOINT"],
            timeout=10)
    if not r.ok:
        return ()
    try:
        import json
        root = json.loads(r.stdout)
        return tuple(root.get("blockdevices", []))
    except json.JSONDecodeError:
        return ()


# ── statvfs (used by Cleaner to get free space) ──────────────────────────────

def free_bytes(path: str = "/") -> int:
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize
    except OSError:
        return 0


def total_bytes(path: str = "/") -> int:
    try:
        st = os.statvfs(path)
        return st.f_blocks * st.f_frsize
    except OSError:
        return 0


def used_bytes(path: str = "/") -> int:
    try:
        st = os.statvfs(path)
        return (st.f_blocks - st.f_bfree) * st.f_frsize
    except OSError:
        return 0


# ── in-process disk usage (replaces du) ──────────────────────────────────────

def dir_size(path: str | os.PathLike) -> int:
    """Sum of file sizes under ``path``. Follows symlinks per :func:`os.walk`.

    Returns 0 if the path doesn't exist or isn't readable. Skips
    mount points and FIFOs to avoid double-counting and hanging.
    """
    root = Path(path)
    if not root.exists():
        return 0
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Don't cross filesystem boundaries
            try:
                if os.stat(dirpath).st_dev != os.stat(root).st_dev:
                    dirnames.clear()
                    continue
            except OSError:
                dirnames.clear()
                continue
            for fname in filenames:
                fp = os.path.join(dirpath, fname)
                try:
                    st = os.lstat(fp)
                except OSError:
                    continue
                if not os.path.isfile(fp) or os.path.islink(fp):
                    continue
                total += st.st_size
    except OSError as exc:
        _log.debug("dir_size(%s) failed: %s", root, exc)
    return total


def walk_real_files(root: str | os.PathLike,
                    *,
                    skip_names: frozenset[str] = frozenset(),
                    max_depth: int | None = None
                    ) -> Iterator[str]:
    """Yield regular files under ``root``, pruning skip dirs in-place."""
    base = Path(root)
    if not base.exists():
        return
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        if max_depth is not None:
            depth = len(Path(dirpath).relative_to(base).parts)
            if depth >= max_depth:
                dirnames.clear()
        dirnames[:] = [d for d in dirnames
                       if d not in skip_names and not d.startswith(".")]
        for fname in filenames:
            fp = os.path.join(dirpath, fname)
            try:
                if not os.path.isfile(fp) or os.path.islink(fp):
                    continue
            except OSError:
                continue
            yield fp