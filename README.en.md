# KYOCERA Client Tool for Linux

[简体中文](README.md) | English

An independent, unofficial Linux client for KYOCERA printers. The project uses
reproducible static evidence from the official Windows Client Tool, real-device
responses, and interoperability tests to implement native status monitoring,
configuration, Wi-Fi setup, and scanning on Linux.

The primary verified model is the **KYOCERA MA2000w**. Main capabilities:

- PJL/TCP 9100, USB `usblp`, and a non-root libusb Printer-class fallback;
- SNMPv1/v2c status, discovery, and Wi-Fi status/AP scanning;
- KM-WSDL network scanning, RAW decoding, and local format export;
- Web/GUI device management, scan presets, configuration baselines, and
  reviewed property writes;
- Simplified Chinese/English UI, manual update checks, and tag-only releases.

[Latest release](https://github.com/yuannancheng/kyocera-client-tool-for-linux/releases/latest)
· [Project status](PROJECT_PROGRESS.md)
· [Feature coverage](docs/official-feature-parity-plan.md)

> This project is independent and unofficial. It is not affiliated with
> Kyocera Corporation. The software is provided under the MIT License without
> warranty, and the authors disclaim liability to the extent permitted by law.

KYOCERA, ECOSYS, MA2000w, and related names belong to their respective owners
and are used only to describe compatibility.

## Status

| Area | Status |
| --- | --- |
| Network/SNMP/USB status | Verified on MA2000w |
| Discovery and multi-device dashboard | Verified |
| KM-WSDL scan and RAW decoding | Verified on MA2000w |
| PNG/PDF/JPEG export | Verified on MA2000w |
| TIFF/XPS/BMP/high-compression PDF | Local encoding and structure tests pass |
| 147 configuration reads and baselines | MA2000w returns 96/147 readable |
| 27 reviewed integer writes | Network verified; USB write path needs physical-device revalidation |
| USB printing/Wi-Fi operations | Verified on MA2000w |
| Push Scan trigger listener | Read-only detection and local execution implemented; real network trigger not closed |
| ADF/duplex/other models | Hardware unavailable; not verified |
| Update checks and release builds | Verified with v0.3.3 |

## Installation

### Wheel or source

```bash
python3 -m pip install --user .
kyocera-gui
```

Pillow is installed as a Python dependency. GTK/WebKit are optional system
packages:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

Without GTK/WebKit, run the browser dashboard:

```bash
python3 -m kyocera_monitor --web --web-open
```

### Debian package

```bash
python3 tools/build_deb.py
PROJECT_VERSION=$(python3 tools/release.py version)
sudo apt install "./dist/kyocera-monitor_${PROJECT_VERSION}-1_all.deb"
```

The Debian build uses only local Python and `dpkg-deb`; it does not contact the
network and does not include Kyocera Windows binaries or installers. See
[`packaging/README.md`](packaging/README.md).

### Desktop menu

```bash
python3 tools/install_desktop.py
python3 tools/install_desktop.py --uninstall
```

## Quick start

```bash
# GUI; a single USB printer can be selected automatically
kyocera-gui

# Web dashboard
python3 -m kyocera_monitor --web --web-open

# Network printer
python3 -m kyocera_monitor --host 192.168.0.220 --gui
python3 -m kyocera_monitor --host 192.168.0.220 --json

# USB
python3 -m kyocera_monitor --list-usb
python3 -m kyocera_monitor --usb --json

# Discovery
python3 -m kyocera_monitor --discover
python3 -m kyocera_monitor --discover --json
```

CLI exit codes:

- `0`: successful query and normal status;
- `1`: no devices/configuration items, or a comparison found differences;
- `2`: connection, protocol, or argument error;
- `3`: the device reports a warning status;
- `4`: `--expect-model` did not match.

## Web/GUI

### Devices and status

- Add an IP manually or discover printers with SNMP/WS-Discovery;
- Multi-device dashboard, persisted device list, and counter CSV export;
- Model, serial, firmware, network, supplies, trays, panel, alerts, and counters;
- Optional browser notifications;
- Automatic USB printer enumeration when no network target is specified.

### Scanning

```bash
python3 -m kyocera_monitor --host 192.168.0.220 --scan \
  --scan-color FULL_COLOR --scan-format png --scan-output /tmp/scan.png

python3 -m kyocera_monitor --host 192.168.0.220 --scan \
  --scan-color GRAYSCALE --scan-format jpeg --scan-output /tmp/scan.jpg
```

The Web/GUI supports background scan jobs, progress stages, and downloads:

- PNG, PDF, JPEG, TIFF, high-compression PDF, XPS, BMP, and RAW;
- Multi-page jobs, busy protection, timeouts, and close-session errors;
- Local presets, absolute output folders, and Push Scan slot mappings.

Device format and local export format are tracked separately. MA2000w returns
its private RAW format even when JPEG is requested, so JPEG is generated from
RAW on Linux; it is not claimed to be byte-identical to device-native JPEG.

### Configuration

The device page follows the official dialog structure:

- Device defaults;
- Paper and media;
- Communication;
- SNMP traps;
- Panel and scanning;
- Fax;
- Wi-Fi.

The UI supports 147 section-scoped reads, private baselines, comparisons, and
27 reviewed integer properties. Each write carries the observed old value,
target value, and explicit confirmation; the same OID is read back and the old
value is restored on failure. Network targets use SNMP SET and USB targets use
the official `KSETOBJ` path.

Configuration snapshots use atomic `0600` writes and may contain communities,
SSIDs, contacts, or locations. They must not be committed to a public
repository. See
[`docs/reverse-engineering/config-write-safety.md`](docs/reverse-engineering/config-write-safety.md).

### Wi-Fi and USB

```bash
python3 -m kyocera_monitor --usb --wifi-status --json
python3 -m kyocera_monitor --usb --wifi-scan --json

KYOCERA_WIFI_PASSWORD='...' python3 -m kyocera_monitor \
  --usb --wifi-connect SSID --wifi-security 4
```

- Wi-Fi state, AP scanning, and connection order follow the official Wi-Fi
  Setup Tool;
- Passwords exist only in the one request and are not written to settings;
- Credential-changing Web APIs accept loopback clients only;
- USB status and Wi-Fi are verified on MA2000w;
- USB ScanReq image retrieval remains experimental; KM-WSDL is the supported
  scan path.

Inspect or create a CUPS queue for a known Kyocera USB printer:

```bash
python3 tools/install_linux_driver.py
python3 tools/install_linux_driver.py --apply
```

## Languages and update checks

The Web/GUI selects language automatically by default:

- `auto` matches `zh*` or `en*` in `Accept-Language`;
- unsupported languages fall back to Simplified Chinese;
- users can manually select Simplified Chinese or English;
- the setting is persisted in `settings.json` and shared by both pages.

Update checks contact the network only after an explicit action:

```bash
kyocera-monitor --check-update
kyocera-monitor --check-update --json
```

Versions are compared semantically and cached for 60 seconds on both the page
and local server. The client first reads `updater/update.json` and falls back
to the GitHub Releases API if the release download domain is unavailable.
Release links must use HTTPS.

## Releases and versioning

`[project].version` in `pyproject.toml` is the single version source and uses
`MAJOR.MINOR.PATCH`. Release tags use `vX.Y.Z`.

```bash
python3 tools/release.py bump patch
NEXT_VERSION=$(python3 tools/release.py version)

python3 tools/release.py check --tag "v${NEXT_VERSION}"
git tag -a "v${NEXT_VERSION}" -m "KYOCERA Client Tool v${NEXT_VERSION}"
git push origin main "v${NEXT_VERSION}"
```

- Normal `main` pushes and PRs run tests only;
- a matching tag builds the wheel, sdist, Debian package, and GitHub Release;
- the release workflow updates `update.json` in the fixed `updater` Release;
- `workflow_dispatch` with a `release_tag` input is available as an explicit
  retry path;
- published tags are not moved or reused.

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and
[`.github/workflows/release.yml`](.github/workflows/release.yml).

## Testing

```bash
python3 -m unittest discover -s tests -v
python3 tools/check_publication.py
```

The current 390 tests cover:

- PJL/SNMP/USB/Wi-Fi/KM-WSDL protocols and device mappings;
- multi-page scan state, RAW decoding, and local export formats;
- Web/GUI caching, settings, configuration baselines, write/readback, and error
  recovery;
- Chinese/English negotiation, update checks, semantic versions, and release
  workflows;
- Debian packaging, desktop files, public-tree compliance, and sensitive-data
  boundaries.

Research regressions that require local `Kyocera/ClientTool` samples are
skipped when those samples are absent. Checked-in TSV files, generated modules,
and independent implementation tests continue to run in CI.

## Research documentation

- [`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md): current state and next steps;
- [`docs/official-feature-parity-plan.md`](docs/official-feature-parity-plan.md):
  coverage of the official 30 features;
- [`docs/architecture.md`](docs/architecture.md): Linux modules and data flow;
- [`docs/reverse-engineering/scan-workflow.md`](docs/reverse-engineering/scan-workflow.md):
  network scanning and Push Scan;
- [`docs/reverse-engineering/usb-path.md`](docs/reverse-engineering/usb-path.md):
  USB printing and scanning paths;
- [`docs/reverse-engineering/wifi.md`](docs/reverse-engineering/wifi.md):
  Wi-Fi protocol and device evidence;
- [`docs/reverse-engineering/clienttool-protocol.md`](docs/reverse-engineering/clienttool-protocol.md):
  Client Tool configuration and object tables;
- [`docs/reverse-engineering/progress-history.md`](docs/reverse-engineering/progress-history.md):
  historical handoffs and experiments.

## Content and security boundaries

- Analyze only `Kyocera/ClientTool` and files that program actively uses;
- production Linux features do not load or redistribute Kyocera DLLs/EXEs;
- unknown fields, unverified states, and unsupported models must remain clearly
  labeled and must not be described as officially compatible;
- the repository excludes original installers, binaries, full decompiler
  output, credentials, and real site data;
- the Web server listens on `127.0.0.1` by default; add access control if using
  `--web-bind 0.0.0.0`.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [NOTICE](NOTICE) for
third-party and trademark notices.

## License

This project uses the [MIT License](LICENSE). The software is provided “as is”
without express or implied warranty. See [LICENSE](LICENSE),
[docs/legal/compliance.md](docs/legal/compliance.md), and
[CONTRIBUTING.md](CONTRIBUTING.md).
