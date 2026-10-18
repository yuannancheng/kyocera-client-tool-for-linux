"""Linux USB printer discovery for the ``usblp`` character devices.

The Windows tool reaches a USB printer through the Kyocera language monitor and
printer spooler, not through a USB device path. On Linux the equivalent raw
path is the kernel ``usblp`` device (``/dev/usb/lp*``), so this module only
discovers and describes those devices.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path

KYOCERA_VENDOR_ID = 0x0482
MA2000W_PRODUCT_ID = 0x0D51


class UsbError(RuntimeError):
    pass


@dataclass(frozen=True)
class UsbPrinter:
    device: str
    vendor_id: int | None = None
    product_id: int | None = None
    manufacturer: str | None = None
    product: str | None = None
    serial: str | None = None
    sysfs: str | None = None

    @property
    def is_kyocera(self) -> bool:
        return self.vendor_id == KYOCERA_VENDOR_ID

    def to_dict(self) -> dict[str, object]:
        return {
            "device": self.device,
            "vendor_id": (
                f"{self.vendor_id:04x}" if self.vendor_id is not None else None
            ),
            "product_id": (
                f"{self.product_id:04x}" if self.product_id is not None else None
            ),
            "manufacturer": self.manufacturer,
            "product": self.product,
            "serial": self.serial,
            "sysfs": self.sysfs,
        }


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _hex_value(path: Path) -> int | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None


def _usb_device_dir(device: str, sysfs_root: Path) -> Path | None:
    """Find the USB device directory above a ``usbmisc/lpN`` interface."""
    name = os.path.basename(device)
    base = sysfs_root / "class" / "usbmisc" / name / "device"
    try:
        current = base.resolve()
    except OSError:
        return None
    for _ in range(6):
        if (current / "idVendor").is_file():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def discover_usb_printers(
    *,
    sysfs_root: str | os.PathLike[str] = "/sys",
    device_glob: str = "/dev/usb/lp*",
) -> list[UsbPrinter]:
    """Return ``/dev/usb/lp*`` devices with best-effort USB identity."""
    root = Path(sysfs_root)
    printers: list[UsbPrinter] = []
    for device in sorted(glob.glob(device_glob)):
        usb_dir = _usb_device_dir(device, root)
        if usb_dir is None:
            printers.append(UsbPrinter(device=device))
            continue
        printers.append(
            UsbPrinter(
                device=device,
                vendor_id=_hex_value(usb_dir / "idVendor"),
                product_id=_hex_value(usb_dir / "idProduct"),
                manufacturer=_read_text(usb_dir / "manufacturer"),
                product=_read_text(usb_dir / "product"),
                serial=_read_text(usb_dir / "serial"),
                sysfs=str(usb_dir),
            )
        )
    return printers


def select_usb_printer(
    printers: list[UsbPrinter],
    *,
    vendor_id: int | None = None,
    product_id: int | None = None,
) -> UsbPrinter:
    """Choose one device deterministically, preferring a Kyocera MA2000w."""
    candidates = [
        printer
        for printer in printers
        if (vendor_id is None or printer.vendor_id == vendor_id)
        and (product_id is None or printer.product_id == product_id)
    ]
    if not candidates:
        if not printers:
            raise UsbError("no /dev/usb/lp* devices found")
        raise UsbError("no USB printer matched the requested VID/PID")

    ma2000w = [
        printer
        for printer in candidates
        if printer.vendor_id == KYOCERA_VENDOR_ID
        and printer.product_id == MA2000W_PRODUCT_ID
    ]
    if len(ma2000w) == 1:
        return ma2000w[0]

    kyocera = [printer for printer in candidates if printer.is_kyocera]
    if len(kyocera) == 1:
        return kyocera[0]
    if len(candidates) == 1:
        return candidates[0]

    listing = ", ".join(printer.device for printer in candidates)
    raise UsbError(
        f"multiple USB printers found ({listing}); select one with --device"
    )
