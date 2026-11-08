#!/usr/bin/env python3
"""Build an installable, architecture-independent Debian package."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "kyocera-monitor"
VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.+:~-]*$")

ENTRY_POINTS = {
    "kyocera-monitor": "from kyocera_monitor.cli import main\nraise SystemExit(main())\n",
    "kyocera-gui": "from kyocera_monitor.gui import main\nraise SystemExit(main())\n",
    "kyocera-kmscn-probe": (
        "from kyocera_monitor.kmscn import main\n"
        "raise SystemExit(main())\n"
    ),
}


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', text)
    if not match:
        raise RuntimeError("pyproject.toml has no project version")
    return match.group(1)


def tree_size(root: Path) -> int:
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def _copy_regular_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def build_package(
    output_directory: Path,
    *,
    version: str,
    revision: str = "1",
    maintainer: str = "screw-up <noreply@users.noreply.github.com>",
    dpkg_deb: str | None = None,
) -> Path:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid Debian version: {version!r}")
    if not re.fullmatch(r"[0-9]+", revision):
        raise ValueError(f"invalid Debian revision: {revision!r}")
    dpkg_deb = dpkg_deb or shutil.which("dpkg-deb")
    if dpkg_deb is None:
        raise RuntimeError("dpkg-deb is required to build the Debian package")

    package_version = f"{version}-{revision}"
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / f"{PACKAGE}_{package_version}_all.deb"

    with tempfile.TemporaryDirectory(prefix="kyocera-deb-build-") as temporary:
        root = Path(temporary) / PACKAGE
        root.mkdir()

        package_directory = (
            root / "usr" / "lib" / "python3" / "dist-packages" / "kyocera_monitor"
        )
        _copy_regular_tree(ROOT / "kyocera_monitor", package_directory)
        (package_directory / "_build_version.py").write_text(
            f'__version__ = "{version}"\n',
            encoding="utf-8",
        )

        binary_directory = root / "usr" / "bin"
        for name, body in ENTRY_POINTS.items():
            _write_executable(
                binary_directory / name,
                "#!/usr/bin/python3\n" + body,
            )

        applications = root / "usr" / "share" / "applications"
        applications.mkdir(parents=True)
        shutil.copy2(
            ROOT / "packaging" / "kyocera-monitor.desktop",
            applications / "kyocera-monitor.desktop",
        )
        icons = (
            root
            / "usr"
            / "share"
            / "icons"
            / "hicolor"
            / "scalable"
            / "apps"
        )
        icons.mkdir(parents=True)
        shutil.copy2(
            ROOT / "packaging" / "kyocera-monitor.svg",
            icons / "kyocera-monitor.svg",
        )
        udev_rules = root / "usr" / "lib" / "udev" / "rules.d"
        udev_rules.mkdir(parents=True)
        shutil.copy2(
            ROOT / "packaging" / "90-kyocera-usb.rules",
            udev_rules / "90-kyocera-usb.rules",
        )
        helper = root / "usr" / "libexec" / PACKAGE
        helper.mkdir(parents=True)
        driver_helper = helper / "install-linux-driver"
        shutil.copy2(
            ROOT / "tools" / "install_linux_driver.py",
            driver_helper,
        )
        driver_helper.chmod(0o755)

        documentation = root / "usr" / "share" / "doc" / PACKAGE
        documentation.mkdir(parents=True)
        for name in ("LICENSE", "NOTICE", "README.md"):
            shutil.copy2(ROOT / name, documentation / name)
        shutil.copy2(
            ROOT / "tools" / "install_linux_driver.py",
            documentation / "install_linux_driver.py",
        )
        shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", documentation / "copyright")

        control_directory = root / "DEBIAN"
        control_directory.mkdir()
        installed_kib = max(1, (tree_size(root) + 1023) // 1024)
        control = (
            f"Package: {PACKAGE}\n"
            f"Version: {package_version}\n"
            "Section: utils\n"
            "Priority: optional\n"
            "Architecture: all\n"
            f"Maintainer: {maintainer}\n"
            "Installed-Size: "
            f"{installed_kib}\n"
            "Depends: python3 (>= 3.10), python3-pil, python3-gi, "
            "gir1.2-gtk-3.0, gir1.2-webkit2-4.1, libusb-1.0-0, "
            "cups-client\n"
            "Homepage: https://github.com/yuannancheng/"
            "kyocera-client-tool-for-linux\n"
            "Description: independent KYOCERA printer client for Linux\n"
            " Monitor device status, manage guarded configuration snapshots,\n"
            " configure Wi-Fi, inspect USB, and scan through verified\n"
            " device services.\n"
            " The application is unofficial and does not include or load\n"
            " Kyocera's original Windows binaries.\n"
        )
        (control_directory / "control").write_text(control, encoding="utf-8")
        _write_executable(
            control_directory / "postinst",
            "#!/bin/sh\n"
            "set -e\n"
            "if command -v udevadm >/dev/null 2>&1; then\n"
            "  udevadm control --reload-rules >/dev/null 2>&1 || true\n"
            "  udevadm trigger --subsystem-match=usbmisc >/dev/null 2>&1 || true\n"
            "  udevadm trigger --subsystem-match=usb >/dev/null 2>&1 || true\n"
            "fi\n",
        )

        source_epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if source_epoch:
            try:
                epoch = int(source_epoch)
            except ValueError as exc:
                raise ValueError("SOURCE_DATE_EPOCH must be an integer") from exc
            for path in root.rglob("*"):
                os.utime(path, (epoch, epoch), follow_symlinks=False)

        command = [dpkg_deb, "--build", "--root-owner-group", str(root), str(destination)]
        subprocess.run(command, check=True, capture_output=True, text=True)

    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="directory for the .deb (default: dist)",
    )
    parser.add_argument(
        "--version",
        default=project_version(),
        help="upstream package version (default: pyproject.toml)",
    )
    parser.add_argument("--revision", default="1", help="Debian revision")
    parser.add_argument(
        "--maintainer",
        default="screw-up <noreply@users.noreply.github.com>",
        help="Debian maintainer field",
    )
    args = parser.parse_args(argv)
    try:
        destination = build_package(
            args.output_dir,
            version=args.version,
            revision=args.revision,
            maintainer=args.maintainer,
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
