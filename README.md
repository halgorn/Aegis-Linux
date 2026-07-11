# Aegis Linux

> The Open Source Linux Performance & Security Suite

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Linux-orange.svg)](#)
[![Status](https://img.shields.io/badge/status-Alpha-yellow.svg)](#)

Aegis Linux is a modern, open-source system optimization, monitoring,
maintenance and security suite designed specifically for Linux.

It combines the best ideas from CCleaner, BleachBit, Glances, Stacer,
btop and Microsoft Sysinternals into one coherent application.

---

## Architecture

Aegis follows **Clean Architecture / Hexagonal** principles:

```
src/aegis/
├── core/         cross-cutting infra (config, logging, concurrency)
├── domain/       pure business models (no I/O, no UI)
├── collectors/   I/O adapters (read /proc, /sys, subprocess, files)
├── services/     use cases (orchestrate collectors + rules)
├── rules/        declarative detection thresholds
├── persistence/  config, history, metrics cache
├── plugins/      plugin system (Fase 8)
├── daemon/       background service (Fase 7)
└── ui/           presentation layer
    ├── theme.py        palette + fonts + theme switching
    ├── widgets/        reusable widgets (cards, charts, gauges)
    └── pages/          one file per page
```

Each module has a single responsibility, exposes a small surface,
and can be tested in isolation. UI never imports collectors
directly — UI talks to services which talk to collectors.

See [`docs/architecture.md`](docs/architecture.md) for details.

---

## Features

### Cleaning
apt, dnf, pacman, zypper caches · snap revisions · flatpak unused
runtimes · pip/npm/yarn/pnpm/cargo/go/gradle caches · docker/podman
build cache · VSCode / JetBrains / Android Studio / Unity / Unreal /
Godot / Steam / Heroic / Wine / Proton / Lutris caches · browsers
(chrome, firefox, brave, edge, opera, vivaldi) · thumbnail, font,
recent files, trash, journalctl, tmp, crash reports, core dumps,
broken symlinks, orphan .desktop, duplicates by hash, large files.

### Performance
CPU governor / frequency / temperature · RAM / Swap / ZRAM / ZSWAP ·
disk I/O scheduler · sysctl (swappiness, THP, NUMA) · TRIM · SMART /
NVMe health · load average / pressure · GPU util + VRAM + temp ·
battery · power profile · fan RPM.

### Monitoring
Real-time metrics with 1Hz refresh, 10-min rolling history, export
to JSON/CSV. Floating overlay widget (Fase 7).

### Security
Open ports / listeners · firewall (ufw, firewalld, nftables) · SSH
config audit · SUID/SGID · world-writable files · cron + systemd
inspection · rootkit hints (rkhunter wrapper) · fail2ban · SELinux /
AppArmor status · /etc/hosts editor · DNS leak check.

### Network
Interfaces, gateway, DNS, ARP, mDNS device discovery, active
connections with GeoIP, bandwidth live, ping, packet loss,
Whois, speedtest, VPN detection.

### Drivers / Firmware
Inventory via `lshw` / `lspci` / `lsusb`, DKMS status, firmware via
`fwupdmgr`, microcode, driver update suggestions.

### Disk
SMART / NVMe / bad blocks / lifetime estimate / temperature,
filesystem fragmentation, snapshots (BTRFS / ZFS), LVM, RAID,
TRIM, mount options.

### Backup
Restore points (BTRFS / ZFS snapshots + config tarballs), rollback,
export settings.

### Startup Manager
systemd user + system services, cron, autostart .desktop, snap,
flatpak, AppImage. Measure boot time, enable/disable, impact
estimate.

### Process Explorer
Tree view (parent PID), CPU/RAM/GPU per process, threads, open
files, sockets, libraries, kill/suspend/resume, nice/affinity.

### AI Assistant (Fase 6)
Offline-first rule engine explaining problems and suggesting
actions. Optional local LLM hook (llama.cpp).

### Plugins (Fase 8)
Entry-point based plugin system. Hooks: pre_clean, post_clean,
register_collector, register_page.

---

## Installation

### From source

```bash
git clone https://github.com/halgorn/Aegis-Linux.git
cd Aegis-Linux
pip install -e .
aegis                       # launch GUI
aegis --headless-clean      # CLI cleanup
aegis --doctor              # health check
```

### Distribution packages (planned)

Flatpak, AppImage, .deb, .rpm, AUR.

---

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
black src tests
mypy src/aegis
pytest
```

---

## Roadmap

See [`docs/roadmap.md`](docs/roadmap.md) for the full phased plan.

Current focus: **Fase 0 → Fase 1** (foundation + domain +
collectors).

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Inspiration

CCleaner · BleachBit · Glances · Stacer · htop · btop · Cockpit ·
KDE System Monitor · GNOME System Monitor · Microsoft Sysinternals ·
System76 firmware utilities.