"""Docker / Podman collectors (no daemon access required, just CLI)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from aegis.core.logging import get_logger
from aegis.core.process import run, which

_log = get_logger("collectors.docker")


@dataclass(slots=True, frozen=True)
class Container:
    id: str
    name: str
    image: str
    status: str
    size: str


@dataclass(slots=True, frozen=True)
class Image:
    repo: str
    tag: str
    id: str
    size: str
    created: str


@dataclass(slots=True, frozen=True)
class Volume:
    name: str
    driver: str
    mountpoint: str


# ── availability ────────────────────────────────────────────────────────────

def docker_available() -> bool:
    return which("docker") is not None


def podman_available() -> bool:
    return which("podman") is not None


# ── containers ──────────────────────────────────────────────────────────────

def list_containers() -> tuple[Container, ...]:
    if not docker_available():
        return ()
    r = run(["docker", "ps", "-a", "--format",
             "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Size}}"],
            timeout=15)
    if not r.ok:
        return ()
    out: list[Container] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        out.append(Container(
            id=parts[0], name=parts[1], image=parts[2],
            status=parts[3], size=parts[4],
        ))
    return tuple(out)


# ── images ──────────────────────────────────────────────────────────────────

def list_images() -> tuple[Image, ...]:
    if not docker_available():
        return ()
    r = run(["docker", "images", "--format",
             "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}"],
            timeout=15)
    if not r.ok:
        return ()
    out: list[Image] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        out.append(Image(
            repo=parts[0], tag=parts[1], id=parts[2],
            size=parts[3], created=parts[4],
        ))
    return tuple(out)


# ── volumes ─────────────────────────────────────────────────────────────────

def list_volumes(dangling_only: bool = False) -> tuple[Volume, ...]:
    if not docker_available():
        return ()
    cmd = ["docker", "volume", "ls", "--format", "{{.Name}}\t{{.Driver}}\t{{.Mountpoint}}"]
    if dangling_only:
        cmd.insert(3, "--filter")
        cmd.insert(4, "dangling=true")
    r = run(cmd, timeout=15)
    if not r.ok:
        return ()
    out: list[Volume] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        out.append(Volume(name=parts[0], driver=parts[1], mountpoint=parts[2]))
    return tuple(out)


# ── system df ───────────────────────────────────────────────────────────────

def system_df() -> str:
    if not docker_available():
        return "docker not installed"
    r = run(["docker", "system", "df"], timeout=15)
    return r.stdout.strip() if r.ok else "—"


# ── actions (caller must confirm with user) ────────────────────────────────

def prune(kind: str) -> tuple[bool, str]:
    """``kind``: 'container', 'image', 'volume', 'network', 'system'."""
    if not docker_available():
        return False, "docker not installed"
    cmd = ["docker", kind, "prune", "-f"]
    r = run(cmd, timeout=120)
    return r.ok, r.stderr.strip() or r.stdout.strip()


def container_action(action: str, target: str) -> tuple[bool, str]:
    """``action``: start / stop / restart / rm."""
    if not docker_available():
        return False, "docker not installed"
    r = run(["docker", action, target], timeout=60)
    return r.ok, r.stderr.strip() or r.stdout.strip()


def remove_image(image_id: str) -> tuple[bool, str]:
    if not docker_available():
        return False, "docker not installed"
    r = run(["docker", "rmi", image_id], timeout=60)
    return r.ok, r.stderr.strip() or r.stdout.strip()


def image_size_for_path(path: str) -> int:
    """Best-effort: extract bytes from a docker size string like ``"1.2GB"``."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]?B)\s*$", path, re.I)
    if not m:
        return 0
    val, unit = float(m.group(1)), m.group(2).upper()
    mult = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(val * mult.get(unit, 1))