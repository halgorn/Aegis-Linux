"""Package collectors — apt, snap, flatpak, pip, npm, yarn, cargo, go.

All collectors return the same shape (:class:`Package` /
:class:`PackageUpdate`) so the UI doesn't need per-manager code.

If a manager isn't installed, the collector returns empty tuples
and logs at DEBUG level. The CLI / UI shows the manager as
"unavailable" rather than crashing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from aegis.core.logging import get_logger
from aegis.core.process import run, which
from aegis.domain.packages import Package, PackageUpdate, PkgManager

_log = get_logger("collectors.packages")


# ── apt ──────────────────────────────────────────────────────────────────────

def apt_installed() -> tuple[Package, ...]:
    """List every installed apt package."""
    if which("dpkg-query") is None:
        return ()
    r = run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"],
            timeout=60)
    if not r.ok:
        return ()
    out: list[Package] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, version, status = parts[0], parts[1], parts[2]
        if "installed" not in status:
            continue
        out.append(Package(manager=PkgManager.APT, name=name, version=version,
                           installed=True))
    return tuple(out)


def apt_upgradable() -> tuple[PackageUpdate, ...]:
    """List pending apt upgrades. Runs ``apt update`` first (quiet)."""
    if which("apt") is None:
        return ()
    _ = run(["apt-get", "update", "-qq"], timeout=60)
    r = run(["apt", "list", "--upgradable", "--quiet=2"], timeout=60)
    if not r.ok:
        return ()
    out: list[PackageUpdate] = []
    for line in r.stdout.splitlines():
        if "/" not in line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name, ver = parts[0].split("/")[0], parts[1]
        out.append(PackageUpdate(pkg=Package(
            manager=PkgManager.APT, name=name, version=ver)))
    return tuple(out)


# ── snap ─────────────────────────────────────────────────────────────────────

def snap_installed() -> tuple[Package, ...]:
    if which("snap") is None:
        return ()
    r = run(["snap", "list"], timeout=15)
    if not r.ok:
        return ()
    out: list[Package] = []
    rows = r.stdout.splitlines()
    for i, line in enumerate(rows):
        if i == 0:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        out.append(Package(manager=PkgManager.SNAP, name=parts[0],
                           version=parts[1], installed=True))
    return tuple(out)


def snap_upgradable() -> tuple[PackageUpdate, ...]:
    if which("snap") is None:
        return ()
    r = run(["snap", "refresh", "--list"], timeout=15)
    if not r.ok or r.returncode != 0:
        return ()
    out: list[PackageUpdate] = []
    rows = r.stdout.splitlines()
    for i, line in enumerate(rows):
        if i == 0:    # header
            continue
        parts = line.split()
        if not parts:
            continue
        ver = parts[2] if len(parts) > 2 else "—"
        cur = parts[1] if len(parts) > 1 else "—"
        out.append(PackageUpdate(pkg=Package(
            manager=PkgManager.SNAP, name=parts[0], version=cur, available=ver)))
    return tuple(out)


def snap_old_revisions() -> tuple[tuple[str, str], ...]:
    """``((name, revision), …)`` for every disabled snap revision."""
    if which("snap") is None:
        return ()
    r = run(["snap", "list", "--all"], timeout=15)
    if not r.ok:
        return ()
    out: list[tuple[str, str]] = []
    for i, line in enumerate(r.stdout.splitlines()):
        if i == 0:
            continue
        parts = line.split()
        if len(parts) >= 6 and "disabled" in " ".join(parts[5:]):
            out.append((parts[0], parts[2]))
    return tuple(out)


# ── flatpak ──────────────────────────────────────────────────────────────────

def flatpak_installed() -> tuple[Package, ...]:
    if which("flatpak") is None:
        return ()
    r = run(["flatpak", "list", "--columns=application,version"],
            timeout=30)
    if not r.ok:
        return ()
    out: list[Package] = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        out.append(Package(manager=PkgManager.FLATPAK, name=parts[0],
                           version=parts[1] if len(parts) > 1 else "—",
                           installed=True))
    return tuple(out)


def flatpak_upgradable() -> tuple[PackageUpdate, ...]:
    if which("flatpak") is None:
        return ()
    r = run(["flatpak", "remote-ls", "--updates",
             "--columns=application,version"], timeout=60)
    if not r.ok:
        return ()
    out: list[PackageUpdate] = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        out.append(PackageUpdate(pkg=Package(
            manager=PkgManager.FLATPAK, name=parts[0],
            version=parts[1] if len(parts) > 1 else "—")))
    return tuple(out)


# ── pip (user packages) ──────────────────────────────────────────────────────

def pip_user_installed() -> tuple[Package, ...]:
    if which("pip3") is None and which("pip") is None:
        return ()
    cmd = "pip3" if which("pip3") else "pip"
    r = run([cmd, "list", "--user", "--format=freeze"], timeout=30)
    if not r.ok:
        return ()
    out: list[Package] = []
    for line in r.stdout.splitlines():
        if "==" not in line:
            continue
        n, v = line.split("==", 1)
        out.append(Package(manager=PkgManager.PIP, name=n.strip(),
                           version=v.strip(), installed=True))
    return tuple(out)


# ── npm ──────────────────────────────────────────────────────────────────────

def npm_global_installed() -> tuple[Package, ...]:
    if which("npm") is None:
        return ()
    r = run(["npm", "list", "-g", "--depth=0", "--json"], timeout=30)
    if not r.ok:
        return ()
    import json
    try:
        root = json.loads(r.stdout)
    except ValueError:
        return ()
    deps = (root or {}).get("dependencies", {}) or {}
    return tuple(Package(manager=PkgManager.NPM, name=n, version=meta.get("version", "—"))
                 for n, meta in deps.items())


# ── cargo ────────────────────────────────────────────────────────────────────

def cargo_installed() -> tuple[Package, ...]:
    if which("cargo") is None:
        return ()
    r = run(["cargo", "install", "--list"], timeout=15)
    if not r.ok:
        return ()
    out: list[Package] = []
    for line in r.stdout.splitlines():
        if not line.startswith(" "):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        out.append(Package(manager=PkgManager.CARGO, name=parts[0],
                           version=parts[1].rstrip(":")))
    return tuple(out)


# ── dispatcher ───────────────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class PkgSummary:
    installed: tuple[Package, ...]
    updates: tuple[PackageUpdate, ...]


def all_packages() -> PkgSummary:
    """Run every installed/upgradable collector in one call."""
    installed: list[Package] = []
    updates: list[PackageUpdate] = []
    for getter in (apt_installed, snap_installed, flatpak_installed,
                   pip_user_installed, npm_global_installed,
                   cargo_installed):
        try:
            installed.extend(getter())
        except Exception:  # noqa: BLE001
            _log.exception("collector %s failed", getter.__name__)
    for getter in (apt_upgradable, snap_upgradable, flatpak_upgradable):
        try:
            updates.extend(getter())
        except Exception:  # noqa: BLE001
            _log.exception("update collector %s failed", getter.__name__)
    return PkgSummary(installed=tuple(installed), updates=tuple(updates))


def managers_available() -> tuple[PkgManager, ...]:
    """Return the package managers actually present on this system."""
    out: list[PkgManager] = []
    table = (
        (PkgManager.APT, "apt"),
        (PkgManager.SNAP, "snap"),
        (PkgManager.FLATPAK, "flatpak"),
        (PkgManager.PIP, "pip3"),
        (PkgManager.PIP, "pip"),
        (PkgManager.NPM, "npm"),
        (PkgManager.CARGO, "cargo"),
        (PkgManager.GO, "go"),
        (PkgManager.GEM, "gem"),
    )
    seen: set[PkgManager] = set()
    for mgr, cmd in table:
        if mgr in seen:
            continue
        if which(cmd) is not None:
            seen.add(mgr)
            out.append(mgr)
    return tuple(out)