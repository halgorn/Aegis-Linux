# Aegis Linux AppImage

Single-file portable build. Requires:

* Linux host (the AppImage embeds glibc and Qt6 — won't run on older kernels)
* Python 3.11+
* `pip install pyinstaller`
* `appimagetool` — get from https://github.com/AppImageCommunity/AppImageKit/releases

## Build

```bash
./packaging/appimage/build.sh            # version from git describe
./packaging/appimage/build.sh v1.0.0     # explicit version
```

Output: `dist/Aegis-Linux-<version>-x86_64.AppImage` (~ 70 MB).

## Run

```bash
chmod +x Aegis-Linux-*.AppImage
./Aegis-Linux-*.AppImage                 # GUI launches
./Aegis-Linux-*.AppImage scan health     # CLI scanner
./Aegis-Linux-*.AppImage --help
```

## Why AppImage?

* One file, drag-and-drop install, no root.
* No system pollution: config under `$HOME/.config/aegis/`, no `/usr` writes.
* Works on Ubuntu, Fedora, Arch, Mint, etc. — same binary.
* Auto-updateable via AppImageUpdate (we'll add a checker later).

## Limitations

* Requires FUSE on the host. If running on a server without FUSE,
  extract with `AppImageExtract` and run `./squashfs-root/usr/bin/aegis`.
* First launch is slow (~ 1s) due to FUSE mount. Subsequent are instant.