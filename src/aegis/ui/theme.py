"""Theme — palette + fonts + helpers.

Two built-in themes (dark, light) and four accents. Shared by both
the Tk fallback and the Qt6 primary UI; the dataclass palette works
in both worlds. Qt-specific helpers (:func:`qss`, :func:`qpalette`)
live at the bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── palette ──────────────────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class Palette:
    bg: str
    bg2: str
    bg3: str
    bg4: str
    fg: str
    fg2: str
    blue: str
    green: str
    red: str
    cyan: str
    yellow: str
    mauve: str
    pink: str
    border: str
    selection: str


DARK = Palette(
    bg="#1e1e2e", bg2="#181825", bg3="#313244", bg4="#45475a",
    fg="#cdd6f4", fg2="#6c7086",
    blue="#89b4fa", green="#a6e3a1", red="#f38ba8",
    cyan="#89dceb", yellow="#f9e2af", mauve="#cba6f7", pink="#f5c2e7",
    border="#45475a", selection="#585b70",
)

LIGHT = Palette(
    bg="#eff1f5", bg2="#e6e9ef", bg3="#ccd0da", bg4="#bcc0cc",
    fg="#4c4f69", fg2="#7c7f93",
    blue="#1e66f5", green="#40a02b", red="#d20f39",
    cyan="#04a5e5", yellow="#df8e1d", mauve="#8839ef", pink="#ea76cb",
    border="#9ca0b0", selection="#acb0be",
)


# ── accent resolver ──────────────────────────────────────────────────────────

_ACCENTS: dict[str, str] = {
    "blue": "#89b4fa",
    "green": "#a6e3a1",
    "mauve": "#cba6f7",
    "pink": "#f5c2e7",
}

# ── state ────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ThemeState:
    name: str = "dark"
    accent: str = "blue"
    palette: Palette = field(default=DARK)


_state = ThemeState()


def apply(name: str = "dark", accent: str = "blue") -> Palette:
    """Set the active theme. Returns the resolved :class:`Palette`."""
    _state.name = name
    _state.accent = accent
    _state.palette = DARK if name == "dark" else LIGHT
    return _state.palette


def current() -> Palette:
    return _state.palette


def font(size: int = 10, bold: bool = False) -> tuple[str, int, str]:
    f = ("Helvetica", size)
    return (f[0], f[1], "bold") if bold else f


# ── colour helpers ───────────────────────────────────────────────────────────

def pct_color(pct: float) -> str:
    """Green / yellow / red based on a 0–100% value."""
    if pct < 60: return _state.palette.green
    if pct < 85: return _state.palette.yellow
    return _state.palette.red


def fmt_bytes(n: int) -> str:
    """Human-readable byte count."""
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_pct(p: float) -> str:
    return f"{p * 100:.0f}%"


# ── Qt helpers (QSS + palette) ────────────────────────────────────────────────

def qss(p: Palette | None = None, accent: str | None = None) -> str:
    """Generate a Qt stylesheet for the given palette + accent."""
    pal = p or _state.palette
    ac = (_ACCENTS.get(accent or _state.accent) or pal.blue).lstrip("#")
    return f"""
    QWidget {{
        background-color: {pal.bg};
        color: {pal.fg};
        font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
        font-size: 10pt;
    }}
    QMainWindow, QDialog {{
        background-color: {pal.bg};
    }}
    QFrame#card {{
        background-color: {pal.bg2};
        border: 1px solid {pal.border};
        border-radius: 10px;
    }}
    QLabel#title {{
        color: {pal.fg};
        font-size: 18pt;
        font-weight: 600;
        padding: 4px 0;
    }}
    QLabel#subtitle {{
        color: {pal.fg2};
        font-size: 10pt;
    }}
    QLabel#kpi_value {{
        color: {pal.fg};
        font-size: 22pt;
        font-weight: 700;
    }}
    QLabel#kpi_label {{
        color: {pal.fg2};
        font-size: 9pt;
        text-transform: uppercase;
    }}
    QLabel#badge_ok {{ color: {pal.green}; font-weight: 600; }}
    QLabel#badge_warn {{ color: {pal.yellow}; font-weight: 600; }}
    QLabel#badge_err {{ color: {pal.red}; font-weight: 600; }}
    QLabel#accent {{ color: #{ac}; }}

    QPushButton {{
        background-color: {pal.bg3};
        color: {pal.fg};
        border: 1px solid {pal.border};
        border-radius: 6px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        background-color: {pal.bg4};
        border-color: #{ac};
    }}
    QPushButton:pressed {{
        background-color: {pal.selection};
    }}
    QPushButton:disabled {{
        color: {pal.fg2};
        background-color: {pal.bg2};
    }}
    QPushButton#primary {{
        background-color: #{ac};
        color: {pal.bg};
        border: none;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{
        background-color: {pal.bg4};
        color: {pal.fg};
    }}
    QPushButton#danger {{
        background-color: {pal.red};
        color: {pal.bg};
        border: none;
        font-weight: 600;
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {pal.bg2};
        color: {pal.fg};
        border: 1px solid {pal.border};
        border-radius: 6px;
        padding: 4px 8px;
        selection-background-color: {pal.selection};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border-color: #{ac};
    }}
    QComboBox::drop-down {{ border: none; }}

    QCheckBox {{
        color: {pal.fg};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 4px;
        border: 1px solid {pal.border};
        background: {pal.bg2};
    }}
    QCheckBox::indicator:checked {{
        background: #{ac};
        border-color: #{ac};
    }}

    QProgressBar {{
        background: {pal.bg2};
        border: 1px solid {pal.border};
        border-radius: 6px;
        text-align: center;
        color: {pal.fg};
        height: 14px;
    }}
    QProgressBar::chunk {{
        background: #{ac};
        border-radius: 6px;
    }}

    QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget {{
        background-color: {pal.bg2};
        color: {pal.fg};
        alternate-background-color: {pal.bg3};
        border: 1px solid {pal.border};
        border-radius: 6px;
        gridline-color: {pal.border};
        selection-background-color: {pal.selection};
        selection-color: {pal.fg};
    }}
    QHeaderView::section {{
        background-color: {pal.bg3};
        color: {pal.fg};
        border: none;
        border-right: 1px solid {pal.border};
        padding: 6px 8px;
        font-weight: 600;
    }}
    QTreeWidget::item, QListWidget::item {{
        padding: 4px 6px;
    }}

    QScrollBar:vertical {{
        background: {pal.bg};
        width: 12px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {pal.bg4};
        border-radius: 6px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {pal.selection}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: {pal.bg};
        height: 12px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {pal.bg4};
        border-radius: 6px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {pal.selection}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QTabWidget::pane {{
        border: 1px solid {pal.border};
        border-radius: 6px;
        top: -1px;
    }}
    QTabBar::tab {{
        background: {pal.bg2};
        color: {pal.fg2};
        padding: 6px 14px;
        border: 1px solid {pal.border};
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}
    QTabBar::tab:selected {{
        background: {pal.bg};
        color: {pal.fg};
        border-bottom: 1px solid {pal.bg};
    }}

    QSplitter::handle {{ background: {pal.border}; }}

    QStatusBar {{
        background: {pal.bg2};
        color: {pal.fg2};
    }}

    QToolTip {{
        background: {pal.bg3};
        color: {pal.fg};
        border: 1px solid {pal.border};
        padding: 4px;
        border-radius: 4px;
    }}
    """


def qpalette(p: Palette | None = None) -> "QPalette":
    """Build a :class:`QPalette` matching the given :class:`Palette`."""
    from PyQt6.QtGui import QColor, QPalette
    pal = p or _state.palette
    qp = QPalette()
    qp.setColor(QPalette.ColorRole.Window, QColor(pal.bg))
    qp.setColor(QPalette.ColorRole.WindowText, QColor(pal.fg))
    qp.setColor(QPalette.ColorRole.Base, QColor(pal.bg2))
    qp.setColor(QPalette.ColorRole.AlternateBase, QColor(pal.bg3))
    qp.setColor(QPalette.ColorRole.Text, QColor(pal.fg))
    qp.setColor(QPalette.ColorRole.Button, QColor(pal.bg3))
    qp.setColor(QPalette.ColorRole.ButtonText, QColor(pal.fg))
    qp.setColor(QPalette.ColorRole.Highlight, QColor(pal.selection))
    qp.setColor(QPalette.ColorRole.HighlightedText, QColor(pal.fg))
    qp.setColor(QPalette.ColorRole.PlaceholderText, QColor(pal.fg2))
    return qp


def hex_to_rgb(p: Palette | None = None, key: str = "blue") -> tuple[int, int, int]:
    """Return (r, g, b) 0-255 for a palette key (no leading #)."""
    pal = p or _state.palette
    val = getattr(pal, key, pal.blue).lstrip("#")
    return int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16)