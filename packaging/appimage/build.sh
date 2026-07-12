#!/usr/bin/env bash
# Build an Aegis-Linux AppImage.
#
# Requirements:
#   * Linux host with PyInstaller, appimagetool.
#   * Python 3.11+, PyQt6, PyQt6-Charts.
#
# Output:
#   dist/Aegis-Linux-x86_64.AppImage (~ 70 MB)
#
# Usage:
#   ./packaging/appimage/build.sh [version]   (default: git describe)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VERSION="${1:-$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || echo dev)}"

cd "$ROOT"
echo "==> Aegis Linux AppImage build (version $VERSION)"

# 1. PyInstaller one-folder bundle (faster startup than --onefile,
#    appimagetool wraps the directory in a single file).
echo "==> PyInstaller bundle"
rm -rf build/AppImage dist/AppImage
mkdir -p build/AppImage dist/AppImage
pyinstaller \
    --noconfirm \
    --clean \
    --name "aegis" \
    --windowed \
    --collect-submodules PyQt6 \
    --collect-submodules PyQt6.QtCharts \
    --paths src \
    --distpath "dist/AppImage" \
    --workpath "build/AppImage" \
    --specpath "build/AppImage" \
    src/aegis/__main__.py

# 2. Build the AppDir skeleton.
APPDIR="dist/AppImage/aegis/aegis.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/aegis" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy the PyInstaller bundle into the AppDir.
cp -r dist/AppImage/aegis/_internal/* "$APPDIR/usr/lib/aegis/"
cat > "$APPDIR/usr/bin/aegis" <<EOF
#!/bin/sh
exec "\$(dirname "\$0")/../lib/aegis/aegis" "\$@"
EOF
chmod +x "$APPDIR/usr/bin/aegis"

# 3. Desktop entry.
cat > "$APPDIR/aegis.desktop" <<EOF
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
cp "$APPDIR/aegis.desktop" "$APPDIR/usr/share/applications/"

# 4. Icon (placeholder - real PNG if you have one).
if [ -f packaging/appimage/aegis.png ]; then
    cp packaging/appimage/aegis.png "$APPDIR/aegis.png"
    cp packaging/appimage/aegis.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/aegis.png"
else
    # Minimal 1x1 transparent PNG fallback so appimagetool is happy.
    python3 -c "
import base64, pathlib
b = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
pathlib.Path('$APPDIR/aegis.png').write_bytes(b)
pathlib.Path('$APPDIR/usr/share/icons/hicolor/256x256/apps/aegis.png').write_bytes(b)
"
fi

# 5. AppRun.
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/aegis" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# 6. Build the AppImage.
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [ -z "$APPIMAGETOOL" ]; then
    echo "error: appimagetool not found. Install from https://github.com/AppImageCommunity/AppImageKit/releases" >&2
    exit 1
fi

OUT="dist/Aegis-Linux-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$OUT"
chmod +x "$OUT"

echo "==> Built: $OUT ($(du -h "$OUT" | cut -f1))"