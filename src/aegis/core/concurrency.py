"""Concurrency primitives for Aegis.

* :class:`TaskRunner` — small thread pool with cancellation and
  progress reporting. Replaces the ``threading.Thread(...)``
  boilerplate scattered through the legacy code.
* :class:`Progress` — immutable snapshot of a running task
  (``done``, ``total``, ``message``). Emitted via the event bus.
"""

from __future__ import annotations

import threading
import tkinter as tk
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
    ``on_done``, ``on_error``) are invoked from worker threads by
    default. If :meth:`set_main_invoker` is called with a callable
    ``invoker(callable, *args)`` that safely schedules ``callable``
    on the Tk main loop, the callbacks are routed through it so
    Tk widget calls are safe.

    A common implementation is :class:`MainThreadInvoker` which uses
    a thread-safe queue drained by the Tk event loop.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._ex = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="aegis-task",
        )
        self._futures: list[Future[Any]] = []
        self._lock = threading.Lock()
        self._main_invoker: Callable[..., Any] | None = None

    def set_main_invoker(self, invoker: Callable[..., Any] | None) -> None:
        self._main_invoker = invoker

    def submit(self, spec: TaskSpec) -> Future[Any]:
        fut = self._ex.submit(self._run, spec)
        with self._lock:
            self._futures.append(fut)
        fut.add_done_callback(self._drop_done)
        return fut

    def cancel_all(self) -> None:
        with self._lock:
            for fut in self._futures:
                _ = fut.cancel()
        self._ex.shutdown(wait=False, cancel_futures=True)

    def shutdown(self, wait: bool = True) -> None:
        self._ex.shutdown(wait=wait)

    def _dispatch(self, fn: Callable[..., Any] | None, *args: Any) -> None:
        if fn is None:
            return
        inv = self._main_invoker
        if inv is None:
            fn(*args)
        else:
            try:
                inv(fn, *args)
            except Exception:  # noqa: BLE001
                _log.exception("main-thread invoker raised")

    # ── internal ──────────────────────────────────────────────────────

    def _run(self, spec: TaskSpec) -> Any:
        _log.debug("task start: %s", spec.name)
        try:
            result = spec.fn(*spec.args, **spec.kwargs)
        except BaseException as exc:  # noqa: BLE001
            _log.warning("task %s failed: %r", spec.name, exc)
            self._dispatch(spec.on_error, exc)
            raise
        else:
            self._dispatch(spec.on_done, result)
            return result
        finally:
            _log.debug("task end: %s", spec.name)

    def _drop_done(self, fut: Future[Any]) -> None:
        with self._lock:
            try:
                self._futures.remove(fut)
            except ValueError:
                pass


class MainThreadInvoker:
    """Bridge worker callbacks onto the Tk main loop.

    Usage::

        bridge = MainThreadInvoker(root)
        runner.set_main_invoker(bridge.invoke)
        # root.after_idle(bridge.start)  # optional — constructor schedules it

    Worker threads call :meth:`invoke(fn, *args)`. The function is
    pushed into a thread-safe queue. The Tk main loop drains the
    queue every 50 ms via ``widget.after``.
    """

    POLL_MS = 50

    def __init__(self, root) -> None:
        import queue
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._root = root
        self._pump = root.after(self.POLL_MS, self._drain)
        # Only react to destruction of the bridge's root window,
        # not to widget recreation inside the tree.
        root.bind("<Destroy>", self._on_destroy, add="+")

    def invoke(self, fn: Callable[..., Any], *args: Any) -> None:
        """Queue a callback for execution on the Tk main thread."""
        self._q.put((fn, args))

    def _drain(self) -> None:
        try:
            while True:
                fn, args = self._q.get_nowait()
                try:
                    fn(*args)
                except Exception:  # noqa: BLE001
                    _log.exception("main-thread callback raised")
        except Exception:  # noqa: BLE001
            pass
        try:
            self._pump = self._root.after(self.POLL_MS, self._drain)
        except tk.TclError:
            pass  # root destroyed

    def _on_destroy(self, event) -> None:
        # Only kill the pump when the *root* window itself is destroyed,
        # not when any descendant widget is torn down. Without this check,
        # any widget redraw would silence the bridge's main-thread callback.
        if event.widget is self._root:
            if self._pump is not None:
                try:
                    self._root.after_cancel(self._pump)
                except tk.TclError:
                    pass
                self._pump = None


# ── helpers ────────────────────────────────────────────────────────────────

def iter_with_cancel(items: Iterable[Any],
                     cancel: threading.Event) -> Iterable[Any]:
    """Yield ``items`` until ``cancel`` is set."""
    for item in items:
        if cancel.is_set():
            return
        yield item