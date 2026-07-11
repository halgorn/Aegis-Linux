"""Aegis plugin entry point (Fase 8 placeholder)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PluginMeta:
    name: str
    version: str
    author: str
    description: str


class Plugin:
    """Base class for Aegis plugins.

    Override only the hooks you care about. Aegis calls them at
    well-defined points; default implementations are no-ops.
    """

    meta = PluginMeta(name="unnamed", version="0.0.0",
                       author="", description="")

    def on_load(self, ctx: Any) -> None:
        """Called once when the plugin is registered."""

    def on_unload(self) -> None:
        """Called when Aegis shuts down."""

    def register_collectors(self) -> dict[str, Any]:
        """Return ``{name: callable}`` of extra data collectors."""
        return {}

    def register_pages(self) -> dict[str, Any]:
        """Return ``{key: PageClass}`` of extra sidebar pages."""
        return {}