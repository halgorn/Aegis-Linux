"""Concurrency primitives for Aegis.

* :class:`TaskRunner` — small thread pool with cancellation and
  progress reporting. Replaces the ``threading.Thread(...)``
  boilerplate scattered through the legacy code.
* :class:`Progress` — immutable snapshot of a running task
  (``done``, ``total``, ``message``). Emitted via the event bus.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from aegis.core.logging import get_logger

_log = get_logger("concurrency")


@dataclass(slots=True, frozen=True)
class Progress:
    """Immutable progress snapshot."""

    done: int
    total: int
    message: str = ""
    pct: float = field(default=0.0)

    @classmethod
    def of(cls, done: int, total: int, message: str = "") -> "Progress":
        pct = (done / total) if total > 0 else 0.0
        return cls(done=done, total=total, message=message, pct=pct)


@dataclass(slots=True)
class TaskSpec:
    """Description of a single cancellable background task."""

    name: str
    fn: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    on_progress: Callable[[Progress], None] | None = None
    on_done: Callable[[Any], None] | None = None
    on_error: Callable[[BaseException], None] | None = None
    _cancel: threading.Event = field(default_factory=threading.Event,
                                     repr=False, compare=False)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


class TaskRunner:
    """Bounded thread pool that runs :class:`TaskSpec` instances.

    The runner is intentionally tiny. Callbacks (``on_progress``,
    ``on_done``, ``on_error``) are invoked from worker threads;
    consumers are responsible for marshalling back to the Tk main
    loop (use ``widget.after(0, ...)``).
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._ex = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="aegis-task",
        )
        self._futures: list[Future[Any]] = []
        self._lock = threading.Lock()

    def submit(self, spec: TaskSpec) -> Future[Any]:
        """Schedule ``spec`` and return its :class:`Future`."""
        fut = self._ex.submit(self._run, spec)
        with self._lock:
            self._futures.append(fut)
        fut.add_done_callback(self._drop_done)
        return fut

    def cancel_all(self) -> None:
        """Signal every running task to stop and drain the pool."""
        with self._lock:
            for fut in self._futures:
                _ = fut.cancel()  # best effort
        self._ex.shutdown(wait=False, cancel_futures=True)

    def shutdown(self, wait: bool = True) -> None:
        self._ex.shutdown(wait=wait)

    # --- internals -------------------------------------------------------

    def _run(self, spec: TaskSpec) -> Any:
        _log.debug("task start: %s", spec.name)
        try:
            result = spec.fn(*spec.args, **spec.kwargs)
        except BaseException as exc:  # noqa: BLE001
            _log.warning("task %s failed: %r", spec.name, exc)
            if spec.on_error is not None:
                try:
                    spec.on_error(exc)
                except Exception:  # noqa: BLE001
                    _log.exception("on_error callback raised")
            raise
        else:
            if spec.on_done is not None:
                try:
                    spec.on_done(result)
                except Exception:  # noqa: BLE001
                    _log.exception("on_done callback raised")
            return result
        finally:
            _log.debug("task end: %s", spec.name)

    def _drop_done(self, fut: Future[Any]) -> None:
        with self._lock:
            try:
                self._futures.remove(fut)
            except ValueError:
                pass

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def iter_with_cancel(items: Iterable[Any],
                         cancel: threading.Event) -> Iterable[Any]:
        """Yield ``items`` until ``cancel`` is set."""
        for item in items:
            if cancel.is_set():
                return
            yield item