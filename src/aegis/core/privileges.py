"""Privilege escalation helpers.

Wraps ``pkexec`` (preferred on desktop Linux) and ``sudo`` so the
rest of the codebase can ask for elevation with a single call and
get back a structured :class:`CmdResult`. Always refuses to run
silently — the caller must opt in by passing ``reason="..."`` so
the user sees why elevation is being requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from aegis.core.process import CmdResult, run


@dataclass(slots=True, frozen=True)
class PrivRequest:
    """Description of an escalation request."""

    argv: tuple[str, ...]
    reason: str
    use_sudo: bool = False


def elevate(argv: Sequence[str], *, reason: str,
            use_sudo: bool = False,
            timeout: float | None = 120.0) -> CmdResult:
    """Run ``argv`` with elevated privileges.

    ``reason`` is forwarded to pkexec's prompt so the user sees
    why the elevation is happening. ``use_sudo=True`` falls back to
    sudo for CLI / headless contexts where polkit isn't available.
    """
    if not reason or not reason.strip():
        raise ValueError("elevate() requires a non-empty reason")

    helper = "sudo" if use_sudo else "pkexec"
    wrapped = [helper, *argv]
    return run(wrapped, timeout=timeout)


def can_escalate() -> bool:
    """True if either pkexec or sudo is available."""
    from aegis.core.process import which
    return which("pkexec") is not None or which("sudo") is not None


def preferred_helper() -> str | None:
    """Return the helper that would be used right now."""
    from aegis.core.process import which
    if which("pkexec") is not None:
        return "pkexec"
    if which("sudo") is not None:
        return "sudo"
    return None