#!/usr/bin/env python3
"""Inspect or install the Linux CUPS queue for a KYOCERA USB MFP."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kyocera_monitor.usb import (  # noqa: E402
    merge_usb_printers,
    discover_usb_printers,
    select_usb_printer,
)
from kyocera_monitor.usb_libusb import discover_libusb_printers  # noqa: E402


PPD_CANDIDATES = (
    Path("/usr/share/ppd/kyocera/Kyocera_MA2000w.ppd"),
    Path("/usr/share/ppd/kyocera/Kyocera_PA2000.ppd"),
    Path("/usr/share/ppd/kyocera/Kyocera_Generic_Monochrome_A3_PCL.ppd"),
)


def choose_ppd() -> Path:
    for path in PPD_CANDIDATES:
        if path.is_file():
            return path
    raise RuntimeError(
        "no compatible KYOCERA PPD found; install the Linux printer driver first"
    )


def queue_devices() -> dict[str, str]:
    executable = shutil.which("lpstat")
    if executable is None:
        return {}
    result = subprocess.run(
        [executable, "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    devices: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.startswith("device for ") or ": " not in line:
            continue
        name, device = line[len("device for ") :].split(": ", 1)
        devices[name.strip()] = device.strip()
    return devices


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "inspect or install a CUPS USB queue for the connected KYOCERA MFP"
        )
    )
    parser.add_argument("--queue", default="Kyocera-MA2000w")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create/update the queue; default is a read-only plan",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace the selected queue when its USB URI differs",
    )
    args = parser.parse_args(argv)

    try:
        printer = select_usb_printer(
            merge_usb_printers(
                discover_usb_printers(), discover_libusb_printers()
            )
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not printer.serial:
        print("error: the selected printer has no USB serial number", file=sys.stderr)
        return 2
    manufacturer = quote(printer.manufacturer or "Kyocera", safe="")
    product = quote(printer.product or "Printer", safe="")
    uri = f"usb://{manufacturer}/{product}?serial={quote(printer.serial, safe='')}"

    lpadmin = shutil.which("lpadmin")
    if lpadmin is None:
        print("error: lpadmin is unavailable; install CUPS first", file=sys.stderr)
        return 2

    devices = queue_devices()
    requested_uri = devices.get(args.queue)
    if (
        requested_uri is not None
        and requested_uri.lower() != uri.lower()
        and not args.force
    ):
        print(
            f"error: CUPS queue {args.queue!r} already uses "
            f"{requested_uri!r}, not {uri!r}; use --force to replace it",
            file=sys.stderr,
        )
        return 2
    existing = [
        name for name, device in devices.items() if device.lower() == uri.lower()
    ]
    if existing and args.queue not in existing and not args.force:
        print(
            "USB queue already exists as: "
            + ", ".join(existing)
            + f"\nrequested queue {args.queue!r} was not created; "
            "use --force to create another queue"
        )
        return 0

    try:
        ppd = choose_ppd()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    base = [lpadmin, "-p", args.queue, "-E", "-v", uri, "-P", str(ppd)]
    commands = [
        base,
        [shutil.which("cupsenable") or "cupsenable", args.queue],
        [shutil.which("cupsaccept") or "cupsaccept", args.queue],
    ]
    print(f"USB device: {printer.device}")
    print(f"USB identity: {printer.vendor_id:04x}:{printer.product_id:04x}")
    print(f"CUPS URI: {uri}")
    print(f"PPD: {ppd}")
    for command in commands:
        print(shlex.join(command))

    if not args.apply:
        print("dry-run only; pass --apply to create or update the queue")
        return 0

    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            print(f"error: {shlex.join(command)} failed: {detail}", file=sys.stderr)
            return result.returncode or 2
    print(f"CUPS queue {args.queue!r} is installed and enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
