#!/usr/bin/env bash
# Build a Debian package for Aegis Linux.
#
# Output: dist/aegis_<version>_all.deb  (or amd64 if you're on x86_64)
#
# Why hand-rolled and not py2deb / stdeb?
#   * We only ship a Python wheel + a desktop entry; no need for
#     a full dh-virtualenv workflow.
#   * Keeps the build deterministic from a single script.
#   * Easy to audit: one bash file, ~100 LOC.
#
# Requirements:
#   * dpkg-deb
#   * python3-pip / python3-venv (for the wheel build)
#   * PyQt6 + PyQt6-Charts (system or pip)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VERSION="${1:-$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || echo dev)}"
ARCH="${ARCH:-$(dpkg --print-architecture 2>/dev/null || echo amd64)}"

cd "$ROOT"
echo "==> Aegis Linux .deb build (version $VERSION, arch $ARCH)"

# 1. Build a wheel so the .deb is hermetic (doesn't depend on
#    whatever PyQt6 the user happens to have on their system).
echo "==> Wheel"
rm -rf build/wheel dist/wheel
mkdir -p build/wheel dist/wheel
python3 -m venv build/wheel/venv
build/wheel/venv/bin/pip install --quiet --upgrade pip build
build/wheel/venv/bin/python -m build --wheel --outdir dist/wheel

# 2. Stage the install tree in build/deb-stage/.
STAGE="build/deb-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN"
mkdir -p "$STAGE/usr/bin"
mkdir -p "$STAGE/usr/lib/aegis"
mkdir -p "$STAGE/usr/share/applications"
mkdir -p "$STAGE/usr/share/doc/aegis"

# Unpack the wheel into /usr/lib/aegis/.
python3 -m zipfile -e dist/wheel/*.whl "$STAGE/usr/lib/aegis/"

# Wrapper script. The wheel's console-script entry-point runs a
# __main__ that fires the GUI - perfect.
cat > "$STAGE/usr/bin/aegis" <<EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/usr/lib/aegis")
from aegis.__main__ import main
sys.exit(main())
EOF
chmod +x "$STAGE/usr/bin/aegis"

# Desktop entry.
cat > "$STAGE/usr/share/applications/aegis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Aegis Linux
GenericName=System Cleaner & Performance Suite
Comment=The Open Source Linux Performance & Security Suite
Exec=aegis %F
Icon=aegis
Categories=System;Utility;Settings;
Terminal=false
StartupNotify=true
EOF

# 3. Debian control file.
cat > "$STAGE/DEBIAN/control" <<EOF
Package: aegis
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.11), libqt6core6, libqt6gui6, libqt6widgets6, libqt6charts6
Recommends: smartmontools
Maintainer: Aegis Linux Developers <dev@aegis-linux.org>
Description: Open Source Linux performance & security suite
 Aegis combines the best ideas from CCleaner, BleachBit, Glances,
 Stacer, btop and Microsoft Sysinternals into one coherent
 application: a system cleaner, monitor, performance tuner and
 security auditor for Linux desktops.
 .
 Runs entirely on the local machine. No data leaves your computer.
EOF

# 4. Conffiles + postinst (refresh desktop database).
cat > "$STAGE/DEBIAN/conffiles" <<EOF
/etc/xdg/aegis/config.json
EOF
mkdir -p "$STAGE/etc/xdg/aegis"

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ -d /usr/share/applications ]; then
    command -v update-desktop-database >/dev/null && \
        update-desktop-database /usr/share/applications || true
fi
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ -d /usr/share/applications ]; then
    command -v update-desktop-database >/dev/null && \
        update-desktop-database /usr/share/applications || true
fi
EOF
chmod 755 "$STAGE/DEBIAN/prerm"

# 5. Copyright (machine-readable).
cat > "$STAGE/usr/share/doc/aegis/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: aegis
Upstream-Contact: dev@aegis-linux.org
Source: https://github.com/halgorn/Aegis-Linux

Files: *
Copyright: $(date +%Y) Aegis Linux Developers
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining
 a copy of this software and associated documentation files (the
 "Software"), to deal in the Software without restriction, including
 without limitation the rights to use, copy, modify, merge, publish,
 distribute, sublicense, and/or sell copies of the Software, and to
 permit persons to whom the Software is furnished to do so, subject
 to the standard MIT license terms.
EOF

# 6. Build the .deb.
mkdir -p dist
OUT="dist/aegis_${VERSION}_${ARCH}.deb"
rm -f "$OUT"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"

echo "==> Built: $OUT ($(du -h "$OUT" | cut -f1))"
echo "    Install: sudo dpkg -i $OUT"
echo "    Remove:  sudo apt remove aegis"