# Aegis Linux — Roadmap

See [Architecture](architecture.md) for the layer model.

## ✅ Fase 0 — Foundation
- [x] `pyproject.toml`, `README.md`, LICENSE, `.gitignore`
- [x] `core/paths.py` (XDG via `platformdirs`)
- [x] `core/logging.py` (rotating file + stream, atomic init)
- [x] `core/config.py` (atomic JSON load/save, forward-compat `_extra`)
- [x] `core/process.py` (`CmdResult`, `run()` no-raise wrapper)
- [x] `core/concurrency.py` (`TaskRunner`, `MainThreadInvoker`)
- [x] `core/privileges.py` (`pkexec`/`sudo` with mandatory reason)
- [x] `core/events.py` (thread-safe `EventBus`)

## ✅ Fase 1 — Domain + Collectors
- [x] `domain/system.py` (MemorySample, CpuSample, SystemSnapshot…)
- [x] `domain/cleaner.py` (CleanTarget/Plan/Result + 29 targets via `rules/`)
- [x] `domain/health.py`, `domain/security.py`, `domain/packages.py`
- [x] `collectors/procfs.py` (meminfo, cpu delta, processes, battery)
- [x] `collectors/sysfs.py` (governors, scheduler, hwmon temps, sysctl)
- [x] `collectors/disks.py` (`df`, `diskstats`, `dir_size` in-process)
- [x] `collectors/filesystem.py` (walker, hash, duplicates, large files)
- [x] `collectors/packages.py` (apt, snap, flatpak, pip, npm, cargo)
- [x] `collectors/logs.py`, `collectors/network.py`
- [x] `collectors/security.py`, `collectors/startup.py`, `collectors/drivers.py`
- [x] `collectors/smart.py`, `collectors/docker.py`, `collectors/integrity.py`,
      `collectors/browser.py`, `collectors/gpu.py`

## ✅ Fase 2 — Services
- [x] `services/cleaner_service.py` (plan + execute + dry-run + undo)
- [x] `services/backup_service.py` (tarball snapshots, TTL pruning)
- [x] `services/health_service.py` (14 probes, composite score)
- [x] `services/security_service.py` (findings aggregator)
- [x] `services/performance_service.py` (tuning recommendations)
- [x] `services/monitor_service.py` (1Hz periodic sampler)

## ✅ Fase 3 — UI
- [x] `ui/theme.py` (dark + light palette, 4 accents)
- [x] `ui/widgets/common.py` (button, Card, ProgressBar, apply_tree_style)
- [x] `ui/widgets/scrollable.py` (per-canvas wheel binding, no `bind_all` leak)
- [x] `ui/widgets/charts.py` (Sparkline, Gauge)
- [x] `ui/widgets/toast.py`, `ui/widgets/confirm_dialog.py`,
      `ui/widgets/sidebar.py`
- [x] `ui/pages/dashboard.py`, `cleaner.py`, `health.py`, `security.py`,
      `monitor.py`, `performance.py`, `network.py`, `disks.py`,
      `drivers.py`, `packages.py`, `startup.py`, `logs.py`,
      `restore_points.py`, `settings.py`
- [x] `ui/app.py` (root window, sidebar nav, lazy page construction)

## ✅ Fase 4 — Reliability
- [x] Backup before destructive ops (configurable)
- [x] `RestorePointsPage` (create / restore / delete)
- [x] Confirm dialog for cleaner (preview + backup + dry-run toggles)
- [x] Toast notifications for async events
- [x] Atomic config save

## ✅ Fase 5 — Expansion
- [x] Startup manager (systemd + autostart + cron)
- [x] Network diagnostics (interfaces, ports, ping, DNS, firewall)
- [x] Disk health (SMART, TRIM, gauges)
- [x] Drivers inventory (PCI/USB/DKMS/microcode/firmware)

## ✅ Fase 10 — Quality (partial)
- [x] 55 unit tests (domain, core, filesystem, cleaner)
- [x] `pytest`, `ruff`, `black`, `mypy` configured in `pyproject.toml`
- [x] GitHub Actions CI matrix on Py 3.11 + 3.12
- [x] `docs/architecture.md`, `docs/roadmap.md`

## 🔄 Fase 6 — AI Assistant
- [ ] Offline rule engine explaining issues
- [ ] Optional local LLM via `llama.cpp`
- [ ] Action suggestions tied to CleanPlan

## 🔄 Fase 7 — Daemon + Floating Widget
- [ ] `scanunityd` running via systemd user unit
- [ ] 1Hz sampler storing history to SQLite
- [ ] Floating always-on-top overlay (CPU/RAM/Net/GPU/Temp)

## 🔄 Fase 8 — Plugins
- [ ] Entry-point discovery (`importlib.metadata`)
- [ ] Hooks: `pre_clean`, `post_clean`, `register_collector`,
      `register_page`
- [ ] Plugin directory under `~/.local/share/aegis-linux/plugins/`

## 🔄 Fase 9 — Distribution Packages
- [ ] Flatpak manifest (`packaging/flatpak/`)
- [ ] AppImage build script
- [ ] Debian package (`packaging/deb/`)
- [ ] AUR PKGBUILD
- [ ] Snap

## 🔄 Fase 11 — Observability
- [ ] Structured JSON log mode
- [ ] Optional opt-in telemetry endpoint
- [ ] In-app metrics dashboard

## Backlog
- BTRFS / ZFS snapshot integration
- Whois / GeoIP lookups
- mDNS device discovery
- Port-knock detection
- Auto-update with GPG signature
- I18n (i18n stub already in `core/`)