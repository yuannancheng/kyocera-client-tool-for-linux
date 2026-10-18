#!/usr/bin/env python3
"""Install or remove the Kyocera monitor desktop entry and icon.

The default prefix is ``~/.local`` so no root privileges are needed.  A custom
prefix is useful for tests, packaging, or a system-wide ``/usr/local`` install.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP_SOURCE = ROOT / "packaging" / "kyocera-monitor.desktop"
ICON_SOURCE = ROOT / "packaging" / "kyocera-monitor.svg"
DESKTOP_NAME = "kyocera-monitor.desktop"
ICON_NAME = "kyocera-monitor.svg"


def target_paths(prefix: Path) -> tuple[Path, Path]:
    desktop = prefix / "share" / "applications" / DESKTOP_NAME
    icon = (
        prefix
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / ICON_NAME
    )
    return desktop, icon


def _write(path: Path, data: bytes, *, force: bool) -> None:
    if path.exists():
        if path.read_bytes() == data:
            return
        if not force:
            raise FileExistsError(
                f"{path} already exists with different content; use --force"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def install(prefix: Path, *, force: bool = False, dry_run: bool = False) -> list[Path]:
    desktop_target, icon_target = target_paths(prefix)
    files = (
        (desktop_target, DESKTOP_SOURCE.read_bytes()),
        (icon_target, ICON_SOURCE.read_bytes()),
    )
    if dry_run:
        return [path for path, _ in files]
    for path, data in files:
        _write(path, data, force=force)
    return [path for path, _ in files]


def uninstall(prefix: Path, *, dry_run: bool = False) -> list[Path]:
    desktop_target, icon_target = target_paths(prefix)
    removed: list[Path] = []
    for path in (desktop_target, icon_target):
        if path.exists():
            if not dry_run:
                path.unlink()
            removed.append(path)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        type=Path,
        default=Path.home() / ".local",
        help="installation prefix (default: ~/.local)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace files that already exist with different content",
    )
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.uninstall:
        if shutil.which("kyocera-gui") is None:
            print(
                "warning: kyocera-gui is not on PATH; install the Python "
                "package before launching the menu entry",
                file=sys.stderr,
            )

    if args.uninstall:
        removed = uninstall(args.prefix, dry_run=args.dry_run)
        for path in removed:
            print(f"remove {path}")
        if not removed:
            print("nothing to remove")
        return 0

    installed = install(
        args.prefix, force=args.force, dry_run=args.dry_run
    )
    for path in installed:
        print(f"install {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
