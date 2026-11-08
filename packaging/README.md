# Linux package builds

## Debian package

The Debian package is architecture-independent Python code. Runtime GTK,
WebKitGTK and Pillow dependencies are declared in `DEBIAN/control` so APT can
install them from the distribution.

```bash
python3 tools/build_deb.py
PROJECT_VERSION=$(python3 tools/release.py version)
sudo apt install "./dist/kyocera-monitor_${PROJECT_VERSION}-1_all.deb"
```

Build without root and without contacting the network. The output path is
printed on stdout. `SOURCE_DATE_EPOCH` is honored when set.

Validation performed by the repository tests:

- parse `dpkg-deb --field` and `dpkg-deb --contents`;
- require the three command entry points, Python package, desktop file, icon
  and license;
- reject bundled vendor binaries and bytecode files.

Normal CI runs Python 3.10 and 3.12 tests without building packages.
[`../.github/workflows/release.yml`](../.github/workflows/release.yml) builds
only when a matching `vX.Y.Z` tag is pushed. It verifies the tag against
`pyproject.toml`, runs tests with Python 3.12, builds the wheel, source archive
and architecture-independent `.deb`, runs the publication check, uploads all
three artifacts, and creates or updates the GitHub Release. Use
`python3 tools/release.py bump patch|minor|major` to update the single project
version before creating the release commit and tag.

The release workflow also publishes
`update.json` to the fixed `updater` Release. It contains the released version
and release page URL used by the application's manual update check. The updater
Release is metadata only; the workflow restores the semantic-version release as
GitHub's latest release after updating it.

## AppImage

An AppImage is a later portability target. It must bundle a compatible Python
interpreter plus GTK, WebKitGTK and Pillow rather than assuming the host has
the Debian package names above. No release pipeline dependency is installed in
the current environment, so the Debian package is the first supported artifact.
