# Linux package builds

## Debian package

The Debian package is architecture-independent Python code. Runtime GTK,
WebKitGTK and Pillow dependencies are declared in `DEBIAN/control` so APT can
install them from the distribution.

```bash
python3 tools/build_deb.py
sudo apt install ./dist/kyocera-monitor_0.2.0-1_all.deb
```

Build without root and without contacting the network. The output path is
printed on stdout. `SOURCE_DATE_EPOCH` is honored when set.

Validation performed by the repository tests:

- parse `dpkg-deb --field` and `dpkg-deb --contents`;
- require the three command entry points, Python package, desktop file, icon
  and license;
- reject bundled vendor binaries and bytecode files.

## AppImage

An AppImage is a later portability target. It must bundle a compatible Python
interpreter plus GTK, WebKitGTK and Pillow rather than assuming the host has
the Debian package names above. No release pipeline dependency is installed in
the current environment, so the Debian package is the first supported artifact.
