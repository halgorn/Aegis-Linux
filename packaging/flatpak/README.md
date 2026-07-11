# Flatpak manifest (placeholder — Fase 9)

Placeholder. Real manifest needs:

- `runtime/org.freedesktop.Platform/23.08`
- `sdk/extension/python3.12`
- Polkit policy file installed under `/app/share/polkit-1/actions/`
- D-Bus activation for the daemon (Fase 7)
- Portal access for filesystem reads

Skeleton:

```yaml
app-id: io.github.halgorn.AegisLinux
runtime: org.freedesktop.Platform
runtime-version: '23.08'
sdk: org.freedesktop.Sdk
command: aegis
finish-args:
  - --filesystem=home
  - --filesystem=/var/cache/apt
  - --filesystem=/var/log
  - --socket=session-bus
  - --talk-name=org.freedesktop.PolicyKit1
modules:
  - name: python
    buildsystem: simple
    build-commands:
      - pip3 install --no-index --find-links=wheels aegis-linux
  - name: aegis
    buildsystem: simple
    sources:
      - type: git
        url: https://github.com/halgorn/Aegis-Linux.git
```