"""Lightweight in-process pub/sub.

Aegis services emit events (scan progress, cleaner result, health
issues). The UI subscribes to them. Events are delivered synchronously
to subscribers in the publisher's thread — keep handlers cheap or
marshal to the main loop yourself.

Thread-safety: subscription / emission is guarded by a lock. Delivery
itself is synchronous, so a slow subscriber blocks the publisher.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar


@dataclass(slots=True, frozen=True)
class Event:
    """Base event payload."""

    name: str
    payload: Any = None
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Handler = Callable[[Event], None]


class EventBus:
    """Process-wide singleton bus.

    Use :func:`bus` to obtain the singleton. Tests can construct
    fresh instances.
    """

    _instances: ClassVar[dict[int, "EventBus"]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}
        self._wild: list[Handler] = []
        self._mu = threading.Lock()

    # --- subscription ---------------------------------------------------

    def on(self, name: str, handler: Handler) -> Callable[[], None]:
        """Subscribe to ``name``. Returns an unsubscribe function."""
        with self._mu:
            self._subs.setdefault(name, []).append(handler)

        def _off() -> None:
            with self._mu:
                if name in self._subs:
                    try:
                        self._subs[name].remove(handler)
                    except ValueError:
                        pass

        return _off

    def on_any(self, handler: Handler) -> Callable[[], None]:
        """Subscribe to every event (useful for logging)."""
        with self._mu:
            self._wild.append(handler)

        def _off() -> None:
            with self._mu:
                try:
                    self._wild.remove(handler)
                except ValueError:
                    pass

        return _off

    # --- emission -------------------------------------------------------

    def emit(self, name: str, payload: Any = None) -> Event:
        """Publish an event; returns the :class:`Event` that was sent."""
        ev = Event(name=name, payload=payload)
        with self._mu:
            handlers = list(self._subs.get(name, ())) + list(self._wild)
        for h in handlers:
            try:
                h(ev)
            except Exception:  # noqa: BLE001
                # A misbehaving subscriber must not break the bus.
                from aegis.core.logging import get_logger
                get_logger("events").exception(
                    "subscriber for %s raised", name
                )
        return ev

    def clear(self) -> None:
        """Drop every subscription (used in tests)."""
        with self._mu:
            self._subs.clear()
            self._wild.clear()


def bus() -> EventBus:
    """Return the process-wide :class:`EventBus` (one per thread)."""
    tid = threading.get_ident()
    with EventBus._lock:
        inst = EventBus._instances.get(tid)
        if inst is None:
            inst = EventBus()
            EventBus._instances[tid] = inst
        return inst


# Standard event names — keep in one place so subscribers/publishers
# cannot drift apart.
class Evt:
    """Namespace for standard event names."""

    SCAN_STARTED = "scan.started"
    SCAN_PROGRESS = "scan.progress"
    SCAN_DONE = "scan.done"
    CLEAN_STARTED = "clean.started"
    CLEAN_PROGRESS = "clean.progress"
    CLEAN_DONE = "clean.done"
    HEALTH_UPDATED = "health.updated"
    METRIC_SAMPLE = "metric.sample"
    SECURITY_FINDING = "security.finding"
    ERROR = "error"
    THEME_CHANGED = "ui.theme_changed"
    NAV_CHANGED = "ui.nav_changed"