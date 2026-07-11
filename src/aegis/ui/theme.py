"""Theme — palette + fonts + helpers.

Two built-in themes (dark, light) and four accents. The theme is
applied at app start; widgets pick colours via :func:`t` (theme)
and :func:`a` (accent).
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