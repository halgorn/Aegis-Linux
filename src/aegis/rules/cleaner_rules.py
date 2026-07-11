"""Declarative cleaner targets.

A ``CleanTarget`` is a declarative description of something that
can be cleaned. The :class:`CleanerService` turns a list of targets
into a plan and executes it. Targets here describe the *what*;
execution lives in the service.

Adding a target = adding a :func:`make_*` factory. Adding a new
category = adding an enum value + grouping in :func:`by_category`.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from aegis.domain.cleaner import (
    CleanCategory,
    CleanKind,
    CleanTarget,
)

_HOME = os.path.expanduser("~")


def _home() -> str:
    """Return the current $HOME, recomputed each call so tests can override."""
    return os.path.expanduser("~")


# ── factories ────────────────────────────────────────────────────────────────

def _expand(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(os.path.expanduser(p) for p in paths)


def _h() -> str:
    """Current $HOME (recomputed each call so tests can monkeypatch)."""
    return os.path.expanduser("~")


def make_trash() -> CleanTarget:
    return CleanTarget(
        id="trash",
        label="Trash",
        description="Recycle bin",
        category=CleanCategory.USER_DATA,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.local/share/Trash/files",
                       f"{_h()}/.local/share/Trash/info"]),
    )


def make_thumbnails() -> CleanTarget:
    return CleanTarget(
        id="thumbnails",
        label="Thumbnail cache",
        description="~/.cache/thumbnails",
        category=CleanCategory.SYSTEM,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/thumbnails"]),
    )


def make_font_cache() -> CleanTarget:
    return CleanTarget(
        id="font_cache",
        label="Font cache",
        description="fontconfig caches",
        category=CleanCategory.SYSTEM,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/fontconfig"]),
    )


def make_recent_files() -> CleanTarget:
    return CleanTarget(
        id="recent_files",
        label="Recent files list",
        description="~/.local/share/recently-used.xbel",
        category=CleanCategory.USER_DATA,
        kind=CleanKind.DELETE_FILES,
        paths=_expand([f"{_h()}/.local/share/recently-used.xbel"]),
    )


def make_shell_history() -> CleanTarget:
    return CleanTarget(
        id="shell_history",
        label="Shell history",
        description="Truncate bash/zsh/fish history",
        category=CleanCategory.USER_DATA,
        kind=CleanKind.TRUNCATE,
        paths=_expand([f"{_h()}/.bash_history",
                       f"{_h()}/.zsh_history",
                       f"{_h()}/.local/share/fish/fish_history"]),
        reversible=True,
    )


def make_journal() -> CleanTarget:
    return CleanTarget(
        id="journal",
        label="systemd journal",
        description="Vacuum to 500M",
        category=CleanCategory.SYSTEM,
        kind=CleanKind.EXEC,
        command=("journalctl", "--vacuum-size=500M"),
        needs_root=True,
    )


def make_apt_cache() -> CleanTarget:
    return CleanTarget(
        id="apt_cache",
        label="APT cache",
        description="/var/cache/apt/archives",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.EXEC,
        command=("apt-get", "clean"),
        needs_root=True,
    )


def make_snap_old() -> CleanTarget:
    return CleanTarget(
        id="snap_old",
        label="Snap old revisions",
        description="Disabled snap revisions",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.EXEC,
        command=("__internal__", "snap_old_revisions"),
        needs_root=True,
    )


def make_flatpak_unused() -> CleanTarget:
    return CleanTarget(
        id="flatpak_unused",
        label="Flatpak unused runtimes",
        description="Runtimes not used by any installed app",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.EXEC,
        command=("flatpak", "uninstall", "--unused", "-y"),
    )


def make_pip_cache() -> CleanTarget:
    return CleanTarget(
        id="pip_cache",
        label="pip cache",
        description="~/.cache/pip",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/pip"]),
    )


def make_npm_cache() -> CleanTarget:
    return CleanTarget(
        id="npm_cache",
        label="npm cache",
        description="~/.npm",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.npm"]),
    )


def make_yarn_cache() -> CleanTarget:
    return CleanTarget(
        id="yarn_cache",
        label="Yarn cache",
        description="~/.cache/yarn",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/yarn"]),
    )


def make_cargo_cache() -> CleanTarget:
    return CleanTarget(
        id="cargo_cache",
        label="Cargo registry",
        description="~/.cargo/registry",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cargo/registry"]),
    )


def make_go_cache() -> CleanTarget:
    return CleanTarget(
        id="go_cache",
        label="Go cache",
        description="~/.cache/go-build",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/go-build"]),
    )


def make_conda_pkgs() -> CleanTarget:
    return CleanTarget(
        id="conda_pkgs",
        label="Conda package cache",
        description="miniconda/anaconda pkgs dirs",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/miniconda3/pkgs",
                       f"{_h()}/anaconda3/pkgs",
                       f"{_h()}/miniconda/pkgs",
                       f"{_h()}/.conda/pkgs"]),
    )


def make_jupyter_cache() -> CleanTarget:
    return CleanTarget(
        id="jupyter_cache",
        label="Jupyter cache",
        description="~/.local/share/jupyter",
        category=CleanCategory.PACKAGE_MGR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.local/share/jupyter",
                       f"{_h()}/.jupyter/lab/workspaces"]),
    )


def make_firefox_cache() -> CleanTarget:
    return CleanTarget(
        id="firefox_cache",
        label="Firefox cache",
        description="~/.cache/mozilla",
        category=CleanCategory.BROWSER,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/mozilla"]),
    )


def make_chrome_cache() -> CleanTarget:
    return CleanTarget(
        id="chrome_cache",
        label="Chrome / Chromium cache",
        description="~/.cache/google-chrome + chromium",
        category=CleanCategory.BROWSER,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/google-chrome",
                       f"{_h()}/.cache/chromium"]),
    )


def make_brave_cache() -> CleanTarget:
    return CleanTarget(
        id="brave_cache",
        label="Brave cache",
        description="~/.cache/BraveSoftware",
        category=CleanCategory.BROWSER,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/BraveSoftware"]),
    )


def make_vscode_cache() -> CleanTarget:
    return CleanTarget(
        id="vscode_cache",
        label="VS Code / Cursor cache",
        description="Cached data per editor",
        category=CleanCategory.EDITOR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.config/Code/Cache",
                       f"{_h()}/.config/Code/CachedData",
                       f"{_h()}/.config/Cursor/Cache",
                       f"{_h()}/.config/Cursor/CachedData"]),
    )


def make_jetbrains_cache() -> CleanTarget:
    return CleanTarget(
        id="jetbrains_cache",
        label="JetBrains caches",
        description="~/.cache/JetBrains",
        category=CleanCategory.EDITOR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/JetBrains"]),
    )


def make_android_cache() -> CleanTarget:
    return CleanTarget(
        id="android_cache",
        label="Android Studio cache",
        description="~/.cache/Google/AndroidStudio*",
        category=CleanCategory.EDITOR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/Google"]),
    )


def make_unity_cache() -> CleanTarget:
    return CleanTarget(
        id="unity_cache",
        label="Unity cache",
        description="Library/cache dirs under Unity projects",
        category=CleanCategory.EDITOR,
        kind=CleanKind.DELETE_CONTENTS,
        paths=(),  # populated dynamically by Unity-aware collector
        enabled_by_default=False,
    )


def make_steam_cache() -> CleanTarget:
    return CleanTarget(
        id="steam_cache",
        label="Steam shader cache",
        description="~/.cache/mesa_shader_cache* + Steam shader cache",
        category=CleanCategory.GAME,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/mesa_shader_cache",
                       f"{_h()}/.steam/steam/shadercache"]),
    )


def make_wine_cache() -> CleanTarget:
    return CleanTarget(
        id="wine_cache",
        label="Wine / Proton cache",
        description="~/.cache/wine + Proton shader cache",
        category=CleanCategory.GAME,
        kind=CleanKind.DELETE_CONTENTS,
        paths=_expand([f"{_h()}/.cache/wine",
                       f"{_h()}/.cache/shadercache"]),
    )


def make_docker_build_cache() -> CleanTarget:
    return CleanTarget(
        id="docker_build_cache",
        label="Docker build cache",
        description="docker builder prune",
        category=CleanCategory.CONTAINER,
        kind=CleanKind.EXEC,
        command=("docker", "builder", "prune", "-f"),
    )


def make_pyc_cache() -> CleanTarget:
    return CleanTarget(
        id="pyc_cache",
        label="Python bytecode (.pyc)",
        description="__pycache__ dirs and .pyc files",
        category=CleanCategory.DEV_TOOL,
        kind=CleanKind.EXEC,
        command=("__internal__", "pyc_clean"),
    )


def make_macos_artifacts() -> CleanTarget:
    return CleanTarget(
        id="macos_artifacts",
        label="macOS artifacts",
        description=".DS_Store files and __MACOSX dirs",
        category=CleanCategory.SYSTEM,
        kind=CleanKind.EXEC,
        command=("__internal__", "macos_clean"),
    )


def make_win_artifacts() -> CleanTarget:
    return CleanTarget(
        id="win_artifacts",
        label="Windows artifacts",
        description="Thumbs.db / desktop.ini files",
        category=CleanCategory.SYSTEM,
        kind=CleanKind.EXEC,
        command=("__internal__", "win_clean"),
    )


# ── registry ────────────────────────────────────────────────────────────────

_TARGET_FACTORIES = (
    make_trash,
    make_thumbnails,
    make_font_cache,
    make_recent_files,
    make_shell_history,
    make_journal,
    make_apt_cache,
    make_snap_old,
    make_flatpak_unused,
    make_pip_cache,
    make_npm_cache,
    make_yarn_cache,
    make_cargo_cache,
    make_go_cache,
    make_conda_pkgs,
    make_jupyter_cache,
    make_firefox_cache,
    make_chrome_cache,
    make_brave_cache,
    make_vscode_cache,
    make_jetbrains_cache,
    make_android_cache,
    make_unity_cache,
    make_steam_cache,
    make_wine_cache,
    make_docker_build_cache,
    make_pyc_cache,
    make_macos_artifacts,
    make_win_artifacts,
)


_TARGETS_CACHE: list[CleanTarget] | None = None


def all_targets() -> tuple[CleanTarget, ...]:
    """Return every static target definition (cached per-process)."""
    global _TARGETS_CACHE
    if _TARGETS_CACHE is None:
        _TARGETS_CACHE = [f() for f in _TARGET_FACTORIES]
    return tuple(_TARGETS_CACHE)


def _reset_cache() -> None:
    """Invalidate the cache (used by tests when HOME changes)."""
    global _TARGETS_CACHE
    _TARGETS_CACHE = None


def by_category() -> dict[CleanCategory, tuple[CleanTarget, ...]]:
    out: dict[CleanCategory, list[CleanTarget]] = {}
    for t in all_targets():
        out.setdefault(t.category, []).append(t)
    return {k: tuple(v) for k, v in out.items()}


def target_by_id(tid: str) -> CleanTarget | None:
    for t in all_targets():
        if t.id == tid:
            return t
    return None