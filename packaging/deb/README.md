# Aegis Linux .deb

Hand-rolled Debian package. Single bash script, no dh-virtualenv.

## Build

```bash
./packaging/deb/build.sh                 # version from git describe
./packaging/deb/build.sh 1.0.0           # explicit version
ARCH=amd64 ./packaging/deb/build.sh      # explicit arch (auto-detected otherwise)
```

Output: `dist/aegis_<version>_<arch>.deb` (~ 6 MB).

## Install / Remove

```bash
sudo dpkg -i dist/aegis_1.0.0_amd64.deb
sudo apt install -f                       # resolve dependencies
aegis                                      # launch the GUI
aegis scan health                          # CLI scanner

sudo apt remove aegis                      # uninstall
```

## What's in it

```
/usr/bin/aegis                          # launcher script
/usr/lib/aegis/                         # hermetic wheel install
/usr/share/applications/aegis.desktop   # menu entry
/usr/share/doc/aegis/copyright          # MIT license
/etc/xdg/aegis/config.json              # system default (conffile)
/var/lib/aegis/backups/                 # cleaner backups
```

## Why hand-rolled?

We only ship a Python wheel + a desktop entry. The official Python
packaging guide for Debian recommends dh-virtualenv for complex apps,
but for a single-entry-point tool that's overkill. This script:

* Builds a wheel in an isolated venv (`build/wheel/venv`).
* Unpacks it into `/usr/lib/aegis/`.
* Wraps it with a 4-line launcher at `/usr/bin/aegis`.
* Registers a desktop entry, postinst, prerm, and conffile.

The .deb is reproducible from the wheel — rebuild it in CI and
diff with `dpkg-deb -c` to verify nothing else snuck in.

## Caveats

* The wheel depends on system `libqt6core6`, `libqt6gui6`, etc.
  Ubuntu 24.04+ has these. For older systems, use the AppImage.
* `Recommends: smartmontools` — installed automatically by apt.