"""Qt widgets — sidebar, cards, toast, charts, common labels/buttons.

Replaces the Tkinter widgets. Single file because they share the
same QSS object names (``#card``, ``#primary``) and small enough to
fit one module.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import (
    QObject,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from typing import Any  # noqa: E402
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygon,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aegis.ui.theme import Palette, current, hex_to_rgb


# ── common ────────────────────────────────────────────────────────────────────

def make_title(text: str, sub: str | None = None) -> QWidget:
    """Page title + optional subtitle, both styled via object names."""
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 12)
    lay.setSpacing(2)
    t = QLabel(text)
    t.setObjectName("title")
    lay.addWidget(t)
    if sub:
        s = QLabel(sub)
        s.setObjectName("subtitle")
        s.setWordWrap(True)
        lay.addWidget(s)
    return wrap


def make_kpi(label: str, value: str = "—", accent: str = "blue") -> QFrame:
    """Compact KPI card: small label + large value."""
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 12, 16, 12)
    lay.setSpacing(4)
    l = QLabel(label.upper())
    l.setObjectName("kpi_label")
    v = QLabel(value)
    v.setObjectName("kpi_value")
    lay.addWidget(l)
    lay.addWidget(v)
    card._value_lbl = v  # type: ignore[attr-defined]
    return card


def make_section(title: str) -> QWidget:
    """Section header inside a page."""
    wrap = QWidget()
    lay = QHBoxLayout(wrap)
    lay.setContentsMargins(0, 12, 0, 6)
    bar = QFrame()
    bar.setFixedWidth(3)
    bar.setStyleSheet(f"background: {current().blue}; border: none;")
    lay.addWidget(bar)
    lay.addSpacing(6)
    lbl = QLabel(title)
    lbl.setStyleSheet("font-size: 12pt; font-weight: 600;")
    lay.addWidget(lbl)
    lay.addStretch()
    return wrap


# ── async scan button ────────────────────────────────────────────────────────

class ScanButton(QPushButton):
    """Push-button that flips to a "Scanning…" state during a background
    task *without* being disabled. Re-clicks cancel the previous task
    and start a new one, so the user always gets feedback."""

    def __init__(self, label: str = "Run scan") -> None:
        super().__init__(label)
        self.setObjectName("primary")
        self.setMouseTracking(True)
        self._idle_label = label
        self._busy_label = label + " · …"
        self._current: Any = None  # current TaskSpec; cancelled on re-click
        # GPU-driven glow on hover — QGraphicsDropShadowEffect is
        # composited by the Qt RHI; just toggling the blur radius
        # triggers a repaint that the GPU handles in <1ms.
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(0)
        self._glow.setOffset(0, 0)
        self._glow.setColor(QColor(*hex_to_rgb(key="blue")))
        self.setGraphicsEffect(self._glow)
        self._glow_anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._glow_anim.setDuration(180)

    def start(self, runner: TaskRunner, fn, bridge: WorkerBridge | None = None,
              *, name: str = "scan", on_done=None, on_error=None) -> None:
        """Spawn a worker task. Cancels any previous one. Pass the
        page's WorkerBridge so finish() can be marshalled back to the
        GUI thread (Qt widgets are not thread-safe across workers)."""
        from aegis.core.concurrency import TaskSpec  # local import (cycle-safe)
        if self._current is not None:
            try:
                self._current.cancel()
            except Exception:
                pass
        self._bridge = bridge
        spec = TaskSpec(
            name=name, fn=fn,
            on_done=self._wrap(on_done),
            on_error=self._wrap_error(on_error),
        )
        self._current = spec
        # setText/setEnabled must run on GUI thread; we are there.
        self.setText(self._busy_label)
        self.setEnabled(True)
        runner.submit(spec)

    def finish(self, ok: bool = True, *, label: str | None = None) -> None:
        # Called on the GUI thread (via bridge.post) — safe to touch Qt widgets.
        self._current = None
        self.setText(label or self._idle_label)
        self.setEnabled(True)

    def _wrap(self, user_done):
        def _done(result):
            if self._bridge is not None:
                self._bridge.post(self.finish, True)
            else:
                self.finish(ok=True)
            if user_done is not None:
                user_done(result)
        return _done

    def _wrap_error(self, user_error):
        def _err(exc):
            if self._bridge is not None:
                self._bridge.post(self.finish, False)
            else:
                self.finish(ok=False)
            if user_error is not None:
                user_error(exc)
        return _err


# ── sidebar ───────────────────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class NavItem:
    key: str
    label: str
    icon: str  # unicode glyph


class Sidebar(QFrame):
    """Left navigation rail — QListWidget styled as a vertical button group."""

    selected = pyqtSignal(str)

    def __init__(self, items: list[NavItem], width: int = 200) -> None:
        super().__init__()
        self.setFixedWidth(width)
        self.setObjectName("sidebar")
        self.setStyleSheet(
            f"QFrame#sidebar {{ background: {current().bg2}; "
            f"border-right: 1px solid {current().border}; }}"
            f"QListWidget {{ background: transparent; border: none; }}"
            f"QListWidget::item {{ padding: 10px 16px; border-radius: 6px; "
            f"margin: 2px 8px; }}"
            f"QListWidget::item:hover {{ background: {current().bg3}; }}"
            f"QListWidget::item:selected {{ background: {current().selection};"
            f"  color: {current().fg}; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(0)

        brand = QLabel("⚛  Aegis Linux")
        brand.setStyleSheet(
            f"font-size: 14pt; font-weight: 700; color: {current().blue};"
            f" padding: 4px 18px 14px 18px; border: none;"
        )
        lay.addWidget(brand)

        self._list = QListWidget()
        for item in items:
            li = QListWidgetItem(f" {item.icon}   {item.label}")
            li.setData(Qt.ItemDataRole.UserRole, item.key)
            li.setSizeHint(QSize(0, 36))
            self._list.addItem(li)
        self._list.setCurrentRow(0)
        self._list.currentItemChanged.connect(self._on_changed)
        lay.addWidget(self._list, 1)

        # Footer
        foot = QLabel("v1.0 · CCleaner-equivalent OSS")
        foot.setStyleSheet(
            f"color: {current().fg2}; font-size: 8pt; padding: 8px 18px;"
            f" border: none;"
        )
        lay.addWidget(foot)

    def _on_changed(self, cur: QListWidgetItem | None, _prev) -> None:
        if cur is None:
            return
        self.selected.emit(cur.data(Qt.ItemDataRole.UserRole))

    def select(self, key: str) -> None:
        for i in range(self._list.count()):
            li = self._list.item(i)
            if li.data(Qt.ItemDataRole.UserRole) == key:
                self._list.setCurrentRow(i)
                return


# ── scroll area ───────────────────────────────────────────────────────────────

class ScrollPage(QScrollArea):
    """A scrollable page wrapper. The actual content goes in ``self.body``."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.setWidget(self.body)
        self._lay = QVBoxLayout(self.body)
        self._lay.setContentsMargins(24, 24, 24, 24)
        self._lay.setSpacing(12)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignTop)


# ── cards ─────────────────────────────────────────────────────────────────────

def card_grid(cols: int = 3) -> QWidget:
    """FlowLayout-style grid container for KPI cards."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)
    w._columns = cols  # type: ignore[attr-defined]
    w._cards: list[QFrame] = []  # type: ignore[attr-defined]
    return w


# ── toast ─────────────────────────────────────────────────────────────────────

class ToastHost(QFrame):
    """Bottom-right floating notifications."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toastHost")
        self.setStyleSheet("background: transparent; border: none;")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 8, 8, 8)
        self._lay.setSpacing(6)
        self.setFixedWidth(320)
        self.hide()

    def show_toast(self, text: str, kind: str = "info", ms: int = 3000) -> None:
        pal = current()
        color = {
            "info": pal.blue,
            "success": pal.green,
            "warn": pal.yellow,
            "error": pal.red,
        }.get(kind, pal.blue)
        t = QLabel(text)
        t.setWordWrap(True)
        t.setStyleSheet(
            f"background: {pal.bg3}; color: {pal.fg};"
            f" border-left: 3px solid {color};"
            f" padding: 8px 12px; border-radius: 6px;"
            f" font-size: 9pt;"
        )
        eff = QGraphicsOpacityEffect(t)
        t.setGraphicsEffect(eff)
        self._lay.addWidget(t)
        self.show()
        # Float bottom-right of parent
        if self.parent():
            pr = self.parent().rect()
            self.move(pr.width() - self.width() - 16,
                      pr.height() - self.sizeHint().height() - 16)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        # Schedule fade out
        QTimer.singleShot(ms, lambda: self._fade(t, eff))

    def _fade(self, t: QLabel, eff: QGraphicsOpacityEffect) -> None:
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(lambda: (self._lay.removeWidget(t), t.deleteLater()))
        anim.start()


# ── charts ────────────────────────────────────────────────────────────────────

class Sparkline(QWidget):
    """Tiny line chart — no axes, no labels. Just the wave."""

    def __init__(self, capacity: int = 60, color_key: str = "blue") -> None:
        super().__init__()
        self._cap = capacity
        self._data: list[float] = []
        self._color_key = color_key
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def push(self, value: float) -> None:
        self._data.append(value)
        if len(self._data) > self._cap:
            self._data = self._data[-self._cap:]
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(200, 56)

    def paintEvent(self, _evt) -> None:  # noqa: N802 — Qt naming
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, g, b = hex_to_rgb(key=self._color_key)
        w, h = self.width(), self.height()
        vmax = max(self._data) or 1.0
        vmin = min(self._data)
        rng = (vmax - vmin) or 1.0
        n = len(self._data)
        path = QPainterPath()
        # Add 4px padding so the line doesn't touch edges
        pad = 4
        for i, v in enumerate(self._data):
            x = pad + (w - 2 * pad) * i / max(n - 1, 1)
            y = pad + (h - 2 * pad) * (1 - (v - vmin) / rng)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        # Fill under
        fill = QPainterPath(path)
        fill.lineTo(w - pad, h - pad)
        fill.lineTo(pad, h - pad)
        fill.closeSubpath()
        p.fillPath(fill, QColor(r, g, b, 38))
        pen = QPen(QColor(r, g, b), 2)
        p.setPen(pen)
        p.drawPath(path)
        p.end()


class Gauge(QWidget):
    """Circular progress gauge, 0..100.

    The arc fills with a :class:`QPropertyAnimation` so the needle
    tweens between values rather than snapping — composited by the
    GPU via the Qt RHI.
    """

    def __init__(self, label: str = "", size: int = 120) -> None:
        super().__init__()
        self._value = 0
        self._label = label
        self._size = size
        self.setFixedSize(size, size + 22)
        # Animation property — gives us value updates on every frame.
        self._anim = QPropertyAnimation(self, b"gaugeValue", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_value(self, v: float) -> None:
        target = max(0.0, min(100.0, v))
        if abs(target - self._value) < 0.5:
            self._value = target
            self.update()
            return
        try:
            self._anim.stop()
        except RuntimeError:
            pass
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(target)
        self._anim.start()

    # Qt property accessed by the animation framework.
    def _get_value(self) -> float:
        return self._value

    def _set_value(self, v: float) -> None:
        self._value = v
        self.update()  # schedule a repaint

    # pyqtProperty is what QPropertyAnimation looks for.
    gaugeValue = pyqtProperty(float, fget=_get_value, fset=_set_value)

    # ── hover glow animation (primary buttons only) ────────────────
    def enterEvent(self, ev):  # noqa: N802
        try:
            self._glow_anim.stop()
        except RuntimeError:
            pass
        self._glow_anim.setStartValue(self._glow.blurRadius())
        self._glow_anim.setEndValue(18)
        self._glow_anim.start()
        super().enterEvent(ev)

    def leaveEvent(self, ev):  # noqa: N802
        try:
            self._glow_anim.stop()
        except RuntimeError:
            pass
        self._glow_anim.setStartValue(self._glow.blurRadius())
        self._glow_anim.setEndValue(0)
        self._glow_anim.start()
        super().leaveEvent(ev)

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size
        rect = QRect(2, 2, s - 4, s - 4)
        # Track
        p.setPen(QPen(QColor(*hex_to_rgb(key="bg4")), 8))
        p.drawArc(rect, 90 * 16, -360 * 16)
        # Arc
        pal = current()
        col = pal.green if self._value < 60 else pal.yellow if self._value < 85 else pal.red
        r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        p.setPen(QPen(QColor(r, g, b, 230), 8, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        span = -int(360 * 16 * (self._value / 100.0))
        p.drawArc(rect, 90 * 16, span)
        # Center text
        f = QFont(self.font())
        f.setPointSize(int(s * 0.22))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(pal.fg))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(self._value)}%")
        # Label below
        if self._label:
            f2 = QFont(self.font())
            f2.setPointSize(8)
            p.setFont(f2)
            p.setPen(QColor(pal.fg2))
            p.drawText(QRect(0, s, s, 20),
                       Qt.AlignmentFlag.AlignCenter, self._label)
        p.end()


# ── worker → UI bridge ────────────────────────────────────────────────────────

class WorkerBridge(QObject):
    """Thread-safe bridge: emit ``invoke`` to schedule a callback on the GUI
    thread. Qt equivalent of the Tk MainThreadInvoker."""

    invoke = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Connect invoke signal to a queued slot on the main thread.
        # When emitter lives on the main thread (which this does), a direct
        # connection already marshals back here, but using QueuedConnection
        # is safe because the receiver (self) lives on main too — actually
        # for that case the docs say to use BlockingQueuedConnection which
        # would deadlock. So we just call directly via a normal signal.
        pass

    def post(self, fn, *args, **kwargs) -> None:
        """Schedule ``fn`` to run on the main thread on the next event loop tick."""
        self.invoke.emit((fn, args, kwargs))