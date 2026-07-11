"""Settings page — theme, monitor Hz, telemetry, AI provider, etc."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from aegis.core.config import Config
from aegis.ui.theme import apply, current, DARK, LIGHT


class SettingsPage(tk.Frame):
    def __init__(self, parent, *, on_apply) -> None:
        super().__init__(parent, bg=current().bg)
        self._cfg = Config.load()
        self._on_apply = on_apply
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=current().bg, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Settings", font=("Helvetica", 18, "bold"),
                 fg=current().fg, bg=current().bg).pack(side="left")

        body = tk.Frame(self, bg=current().bg, padx=16, pady=8)
        body.pack(fill="both", expand=True)

        # Theme
        self._theme_var = tk.StringVar(value=self._cfg.theme)
        tk.Label(body, text="Theme", fg=current().fg, bg=current().bg,
                 font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(8, 2))
        for val, label in (("dark", "Dark"), ("light", "Light")):
            tk.Radiobutton(body, text=label, variable=self._theme_var,
                           value=val, bg=current().bg, fg=current().fg,
                           activebackground=current().bg,
                           selectcolor=current().bg4,
                           font=("Helvetica", 10)).pack(anchor="w")

        # Accent
        self._accent_var = tk.StringVar(value=self._cfg.accent)
        tk.Label(body, text="Accent", fg=current().fg, bg=current().bg,
                 font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(12, 2))
        row = tk.Frame(body, bg=current().bg)
        row.pack(anchor="w")
        for val, color in (("blue", current().blue),
                            ("green", current().green),
                            ("mauve", current().mauve),
                            ("pink", current().pink)):
            tk.Radiobutton(row, text=val, variable=self._accent_var, value=val,
                           bg=current().bg, fg=color,
                           activebackground=current().bg,
                           selectcolor=current().bg4,
                           font=("Helvetica", 10)).pack(side="left", padx=6)

        # Monitor
        tk.Label(body, text="Monitor", fg=current().fg, bg=current().bg,
                 font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(12, 2))
        hz_frame = tk.Frame(body, bg=current().bg)
        hz_frame.pack(anchor="w")
        self._hz_var = tk.DoubleVar(value=self._cfg.monitor_refresh_hz)
        for hz in (0.5, 1.0, 2.0, 5.0):
            tk.Radiobutton(hz_frame, text=f"{hz} Hz",
                           variable=self._hz_var, value=hz,
                           bg=current().bg, fg=current().fg,
                           activebackground=current().bg,
                           selectcolor=current().bg4,
                           font=("Helvetica", 10)).pack(side="left", padx=6)

        # Backup
        tk.Label(body, text="Cleanup", fg=current().fg, bg=current().bg,
                 font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(12, 2))
        self._backup_var = tk.BooleanVar(value=self._cfg.create_backup_before_clean)
        tk.Checkbutton(body, text="Create backup before cleanup",
                       variable=self._backup_var, bg=current().bg, fg=current().fg,
                       activebackground=current().bg, selectcolor=current().bg4,
                       font=("Helvetica", 10)).pack(anchor="w")
        self._confirm_var = tk.BooleanVar(value=self._cfg.confirm_destructive)
        tk.Checkbutton(body, text="Always confirm destructive ops",
                       variable=self._confirm_var, bg=current().bg, fg=current().fg,
                       activebackground=current().bg, selectcolor=current().bg4,
                       font=("Helvetica", 10)).pack(anchor="w")
        self._dry_var = tk.BooleanVar(value=self._cfg.dry_run_by_default)
        tk.Checkbutton(body, text="Dry-run by default",
                       variable=self._dry_var, bg=current().bg, fg=current().fg,
                       activebackground=current().bg, selectcolor=current().bg4,
                       font=("Helvetica", 10)).pack(anchor="w")

        # AI
        tk.Label(body, text="AI Assistant", fg=current().fg, bg=current().bg,
                 font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(12, 2))
        self._ai_var = tk.StringVar(value=self._cfg.ai_provider)
        for v, label in (("offline", "Offline (rules only)"),
                          ("local", "Local LLM"),
                          ("cloud", "Cloud (TBD)")):
            tk.Radiobutton(body, text=label, variable=self._ai_var, value=v,
                           bg=current().bg, fg=current().fg,
                           activebackground=current().bg,
                           selectcolor=current().bg4,
                           font=("Helvetica", 10)).pack(anchor="w")

        # Save
        bar = tk.Frame(self, bg=current().bg2, pady=8)
        bar.pack(fill="x", side="bottom")
        from aegis.ui.widgets.common import button as mkbtn
        mkbtn(bar, "Apply & save", bg=current().green, fg=current().bg,
              command=self._save).pack(side="right", padx=14)