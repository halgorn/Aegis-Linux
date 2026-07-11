# Debian packaging (Fase 9)

Plan:

1. `py2deb` or manual `dh_virtualenv` for the binary.
2. Polkit policy at `/usr/share/polkit-1/actions/io.aegis.linux.policy`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
  "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
  "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <action id="io.aegis.linux.pkexec">
    <description>Aegis Linux privileged operations</description>
    <message>Authentication is required to run Aegis privileged actions</message>
    <defaults>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/bin/pkexec</annotate>
  </action>
</policyconfig>
```

3. `.desktop` entry under `/usr/share/applications/`.
4. Optional systemd user unit for the daemon (Fase 7).