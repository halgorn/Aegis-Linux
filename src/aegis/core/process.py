"""Subprocess wrapper with timeout, capture, cancellation.

The stdlib ``subprocess`` API is fine but every call site repeats
the same ``try/except/timeout=None/capture_output=True`` boilerplate.
This module centralises it.

Key guarantees:

* Never raises on a failing command — returns :class:`CmdResult`
  with ``ok=False``.
* Honours ``$LC_ALL=C`` for parsing tool output consistently.
* Encapsulates ``shell=False`` by default; ``shell=True`` is only
  accepted when ``allow_shell=True`` is passed (security gate).
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(slots=True, frozen=True)
class CmdResult:
    """Outcome of a subprocess invocation."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def lines(self) -> list[str]:
        return [ln for ln in self.stdout.splitlines() if ln.strip()]


def run(
    argv: Sequence[str] | str,
    *,
    timeout: float | None = 30.0,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    input: str | None = None,
    check: bool = False,
    allow_shell: bool = False,
) -> CmdResult:
    """Run ``argv`` and return a :class:`CmdResult`.

    ``argv`` may be a string only if ``allow_shell=True``. Otherwise
    a list of arguments is required and ``shell=False`` is enforced.
    """
    import time

    if isinstance(argv, str):
        if not allow_shell:
            raise ValueError(
                "string argv requires allow_shell=True (security gate)"
            )
        cmd: str | Sequence[str] = argv
        use_shell = True
    else:
        cmd = tuple(argv)
        use_shell = False

    merged_env = {**os.environ, "LC_ALL": "C", **(env or {})}
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
            cwd=cwd,
            input=input,
            check=check,
        )
        return CmdResult(
            argv=tuple(argv) if isinstance(argv, (list, tuple)) else (argv,),
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except subprocess.TimeoutExpired:
        return CmdResult(
            argv=tuple(argv) if isinstance(argv, (list, tuple)) else (argv,),
            returncode=-1,
            stdout="",
            stderr=f"timeout after {timeout}s",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except FileNotFoundError as exc:
        return CmdResult(
            argv=tuple(argv) if isinstance(argv, (list, tuple)) else (argv,),
            returncode=-2,
            stdout="",
            stderr=f"not found: {exc}",
            duration_ms=0,
        )
    except OSError as exc:
        return CmdResult(
            argv=tuple(argv) if isinstance(argv, (list, tuple)) else (argv,),
            returncode=-3,
            stdout="",
            stderr=f"OS error: {exc}",
            duration_ms=0,
        )


def which(cmd: str) -> str | None:
    """Return absolute path or ``None`` if not on ``$PATH``."""
    return shutil_which(cmd)


def quote(args: Sequence[str]) -> str:
    """Shell-quote a list of args for safe ``bash -c`` usage."""
    return " ".join(shlex.quote(a) for a in args)


# Local import to avoid leaking shutil into the module namespace.
from shutil import which as shutil_which  # noqa: E402