"""Domain model — system cleaning.

A :class:`CleanTarget` is a declarative description of something
that can be cleaned. Collectors can add targets dynamically (e.g.
when a new browser is installed). The :class:`CleanerService`
builds a :class:`CleanPlan` from selected targets, then executes
it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Sequence


class CleanKind(str, Enum):
    """How to clean a target."""

    DELETE_CONTENTS = "delete_contents"   # shutil.rmtree on the dir
    DELETE_FILES = "delete_files"         # os.remove each file
    TRUNCATE = "truncate"                 # empty out the file
    EXEC = "exec"                         # run a command (apt clean, …)


class CleanCategory(str, Enum):
    """Where the target fits in the UI taxonomy."""

    SYSTEM = "system"
    BROWSER = "browser"
    PACKAGE_MGR = "package_mgr"
    DEV_TOOL = "dev_tool"
    EDITOR = "editor"
    GAME = "game"
    CONTAINER = "container"
    MEDIA = "media"
    USER_DATA = "user_data"


@dataclass(slots=True, frozen=True)
class CleanTarget:
    """A single thing that can be cleaned."""

    id: str
    label: str
    description: str
    category: CleanCategory
    kind: CleanKind
    paths: tuple[str, ...] = ()
    command: tuple[str, ...] = ()        # used when kind == EXEC
    needs_root: bool = False
    reversible: bool = False             # true → can be undone via backup
    estimated_size: int = 0              # bytes; 0 = unknown
    enabled_by_default: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("CleanTarget.id is required")
        if self.kind in (CleanKind.DELETE_CONTENTS, CleanKind.DELETE_FILES,
                         CleanKind.TRUNCATE) and not self.paths:
            raise ValueError(
                f"CleanTarget {self.id!r} needs at least one path"
            )
        if self.kind == CleanKind.EXEC and not self.command:
            raise ValueError(
                f"CleanTarget {self.id!r} with kind=EXEC needs a command"
            )


@dataclass(slots=True)
class CleanPlan:
    """A list of targets the user agreed to clean."""

    targets: list[CleanTarget]
    dry_run: bool = False
    create_backup: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_estimated_bytes(self) -> int:
        return sum(t.estimated_size for t in self.targets)

    def by_category(self) -> dict[CleanCategory, list[CleanTarget]]:
        out: dict[CleanCategory, list[CleanTarget]] = {}
        for t in self.targets:
            out.setdefault(t.category, []).append(t)
        return out


@dataclass(slots=True, frozen=True)
class CleanRecord:
    """One entry of the cleanup history log."""

    target_id: str
    label: str
    bytes_freed: int
    files_removed: int
    started_at: datetime
    finished_at: datetime
    ok: bool
    error: str = ""
    backup_path: str = ""


@dataclass(slots=True)
class CleanResult:
    """Outcome of executing a :class:`CleanPlan`."""

    records: list[CleanRecord] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.records)

    @property
    def bytes_freed(self) -> int:
        return sum(r.bytes_freed for r in self.records if r.ok)

    @property
    def files_removed(self) -> int:
        return sum(r.files_removed for r in self.records if r.ok)

    def to_text(self) -> str:
        lines = [
            f"Aegis cleanup — {len(self.records)} target(s)",
            f"  bytes freed:  {self.bytes_freed:,}",
            f"  files removed: {self.files_removed:,}",
            "",
        ]
        for r in self.records:
            mark = "✓" if r.ok else "✗"
            lines.append(
                f"  {mark} {r.label:<28} "
                f"{r.bytes_freed:>10,} B  {r.files_removed:>6} files"
            )
            if r.error:
                lines.append(f"      error: {r.error}")
        return "\n".join(lines)


@dataclass(slots=True, frozen=True)
class DuplicateGroup:
    """A set of paths that share the same content hash."""

    hash: str
    paths: tuple[str, ...]
    size: int

    @property
    def savings(self) -> int:
        return self.size * max(0, len(self.paths) - 1)


@dataclass(slots=True, frozen=True)
class LargeFile:
    path: str
    size: int
    mtime: datetime