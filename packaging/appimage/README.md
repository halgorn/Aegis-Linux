# AppImage build script (Fase 9)

Plan:

```bash
# 1. Build a relocatable Python runtime with PyInstaller
pyinstaller --noconfirm --windowed --name aegis \
    --collect-submodules aegis \
    src/aegis/__main__.py

# 2. Bundle in a minimal AppDir
mkdir -p AppDir/usr/bin AppDir/usr/share/applications
cp dist/aegis/aegis AppDir/usr/bin/
cp packaging/aegis.desktop AppDir/usr/share/applications/
cp assets/icons/256x256/aegis.png AppDir/aegis.png

# 3. Use linuxdeploy to wrap in an AppImage
linuxdeploy --appdir AppDir \
    --output appimage \
    --desktop-file packaging/aegis.desktop \
    --icon-file assets/icons/256x256/aegis.png
```

CI integration: `.github/workflows/appimage.yml` runs the script on
tag pushes.