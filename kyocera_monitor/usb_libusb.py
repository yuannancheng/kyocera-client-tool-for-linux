"""Direct libusb access to Kyocera USB printer-class interfaces.

The kernel ``usblp`` path is preferred when its character device is readable.
Some desktop sessions do not grant the user access to ``/dev/usb/lp*`` even
though the USB usbfs nodes are available.  This module provides a narrow
ctypes-backed fallback for the standard printer-class interface, using the
same UEL/PJL bytes as the normal ``usblp`` transport.

It intentionally only claims interface 0 (USB Printer class), never the
vendor-specific scanner interface.  The kernel driver is detached for the
duration of the operation and reattached automatically by libusb on release.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import time
from dataclasses import dataclass
from pathlib import Path

from .usb import UsbPrinter


class LibusbError(RuntimeError):
    pass


class _EndpointDescriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bEndpointAddress", ctypes.c_uint8),
        ("bmAttributes", ctypes.c_uint8),
        ("wMaxPacketSize", ctypes.c_uint16),
        ("bInterval", ctypes.c_uint8),
        ("bRefresh", ctypes.c_uint8),
        ("bSynchAddress", ctypes.c_uint8),
        ("extra", ctypes.c_void_p),
        ("extra_length", ctypes.c_int),
    ]


class _InterfaceDescriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bInterfaceNumber", ctypes.c_uint8),
        ("bAlternateSetting", ctypes.c_uint8),
        ("bNumEndpoints", ctypes.c_uint8),
        ("bInterfaceClass", ctypes.c_uint8),
        ("bInterfaceSubClass", ctypes.c_uint8),
        ("bInterfaceProtocol", ctypes.c_uint8),
        ("iInterface", ctypes.c_uint8),
        ("endpoint", ctypes.POINTER(_EndpointDescriptor)),
        ("extra", ctypes.c_void_p),
        ("extra_length", ctypes.c_int),
    ]


class _Interface(ctypes.Structure):
    _fields_ = [
        ("altsetting", ctypes.POINTER(_InterfaceDescriptor)),
        ("num_altsetting", ctypes.c_int),
    ]


class _ConfigDescriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("wTotalLength", ctypes.c_uint16),
        ("bNumInterfaces", ctypes.c_uint8),
        ("bConfigurationValue", ctypes.c_uint8),
        ("iConfiguration", ctypes.c_uint8),
        ("bmAttributes", ctypes.c_uint8),
        ("bMaxPower", ctypes.c_uint8),
        ("interface", ctypes.POINTER(_Interface)),
        ("extra", ctypes.c_void_p),
        ("extra_length", ctypes.c_int),
    ]


class _DeviceDescriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16),
        ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8),
        ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8),
        ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16),
        ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8),
        ("iProduct", ctypes.c_uint8),
        ("iSerial", ctypes.c_uint8),
        ("bNumConfigurations", ctypes.c_uint8),
    ]


_ERROR_NAMES = {
    -1: "I/O error",
    -2: "invalid parameter",
    -3: "access denied",
    -4: "device disappeared",
    -5: "device not found",
    -6: "busy",
    -7: "timeout",
    -8: "pipe error",
    -9: "overflow",
    -10: "interrupted",
    -11: "out of memory",
    -12: "unsupported operation",
    -99: "other error",
}


def _error(code: int, operation: str) -> LibusbError:
    detail = _ERROR_NAMES.get(code, f"libusb error {code}")
    return LibusbError(f"{operation}: {detail}")


def _load_library() -> ctypes.CDLL:
    name = ctypes.util.find_library("usb-1.0")
    if not name:
        raise LibusbError("libusb-1.0 is not installed")
    library = ctypes.CDLL(name)
    library.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.libusb_init.restype = ctypes.c_int
    library.libusb_exit.argtypes = [ctypes.c_void_p]
    library.libusb_get_device_list.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ]
    library.libusb_get_device_list.restype = ctypes.c_ssize_t
    library.libusb_free_device_list.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_int,
    ]
    library.libusb_get_device_descriptor.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_DeviceDescriptor),
    ]
    library.libusb_get_device_descriptor.restype = ctypes.c_int
    library.libusb_get_bus_number.argtypes = [ctypes.c_void_p]
    library.libusb_get_bus_number.restype = ctypes.c_uint8
    library.libusb_get_device_address.argtypes = [ctypes.c_void_p]
    library.libusb_get_device_address.restype = ctypes.c_uint8
    library.libusb_get_active_config_descriptor.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(_ConfigDescriptor)),
    ]
    library.libusb_get_active_config_descriptor.restype = ctypes.c_int
    library.libusb_free_config_descriptor.argtypes = [
        ctypes.POINTER(_ConfigDescriptor)
    ]
    library.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    library.libusb_open.restype = ctypes.c_int
    library.libusb_close.argtypes = [ctypes.c_void_p]
    library.libusb_set_auto_detach_kernel_driver.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    library.libusb_set_auto_detach_kernel_driver.restype = ctypes.c_int
    library.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.libusb_claim_interface.restype = ctypes.c_int
    library.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.libusb_release_interface.restype = ctypes.c_int
    library.libusb_bulk_transfer.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ubyte,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
    ]
    library.libusb_bulk_transfer.restype = ctypes.c_int
    return library


def _sysfs_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _sysfs_identity(bus: int, address: int) -> dict[str, str | None]:
    """Read portable identity strings without issuing USB string requests."""
    empty: dict[str, str | None] = {
        "manufacturer": None,
        "product": None,
        "serial": None,
    }
    root = Path("/sys/bus/usb/devices")
    try:
        entries = root.iterdir()
    except OSError:
        return empty
    for entry in entries:
        bus_text = _sysfs_text(entry / "busnum")
        address_text = _sysfs_text(entry / "devnum")
        if bus_text != str(bus) or address_text != str(address):
            continue
        return {
            "manufacturer": _sysfs_text(entry / "manufacturer"),
            "product": _sysfs_text(entry / "product"),
            "serial": _sysfs_text(entry / "serial"),
        }
    return empty


def _get_descriptor(
    library: ctypes.CDLL, device: ctypes.c_void_p
) -> tuple[_DeviceDescriptor, int, int]:
    descriptor = _DeviceDescriptor()
    code = library.libusb_get_device_descriptor(device, ctypes.byref(descriptor))
    if code < 0:
        raise _error(code, "read USB device descriptor")
    return (
        descriptor,
        int(library.libusb_get_bus_number(device)),
        int(library.libusb_get_device_address(device)),
    )


def _has_printer_interface(library: ctypes.CDLL, device: ctypes.c_void_p) -> bool:
    config = ctypes.POINTER(_ConfigDescriptor)()
    code = library.libusb_get_active_config_descriptor(device, ctypes.byref(config))
    if code < 0:
        return False
    try:
        for index in range(config.contents.bNumInterfaces):
            interface = config.contents.interface[index]
            for alt_index in range(interface.num_altsetting):
                alternate = interface.altsetting[alt_index]
                if (
                    alternate.bInterfaceClass == 7
                    and alternate.bInterfaceProtocol == 2
                ):
                    return True
        return False
    finally:
        library.libusb_free_config_descriptor(config)


def discover_libusb_printers() -> list[UsbPrinter]:
    """Return Kyocera USB printer-class devices visible through libusb."""
    try:
        library = _load_library()
    except LibusbError:
        return []

    context = ctypes.c_void_p()
    code = library.libusb_init(ctypes.byref(context))
    if code < 0:
        return []
    devices = ctypes.POINTER(ctypes.c_void_p)()
    count = library.libusb_get_device_list(context, ctypes.byref(devices))
    if count < 0:
        library.libusb_exit(context)
        return []
    result: list[UsbPrinter] = []
    try:
        for index in range(count):
            device = devices[index]
            try:
                descriptor, bus, address = _get_descriptor(library, device)
            except LibusbError:
                continue
            if descriptor.idVendor != 0x0482:
                continue
            if not _has_printer_interface(library, device):
                continue
            identity = _sysfs_identity(bus, address)
            result.append(
                UsbPrinter(
                    device=f"libusb:{bus:03d}:{address:03d}",
                    vendor_id=descriptor.idVendor,
                    product_id=descriptor.idProduct,
                    manufacturer=identity["manufacturer"],
                    product=identity["product"],
                    serial=identity["serial"],
                )
            )
    finally:
        library.libusb_free_device_list(devices, 1)
        library.libusb_exit(context)
    return result


@dataclass(frozen=True)
class _EndpointPair:
    interface: int
    bulk_in: int
    bulk_out: int


class LibusbChannel:
    """Bidirectional PJL channel over the USB Printer class interface."""

    def __init__(self, selector: str, *, timeout_ms: int = 5000):
        if not selector.startswith("libusb:"):
            raise LibusbError(f"invalid libusb selector: {selector!r}")
        try:
            _, bus_text, address_text = selector.split(":", 2)
            self.bus = int(bus_text, 10)
            self.address = int(address_text, 10)
        except (TypeError, ValueError) as exc:
            raise LibusbError(f"invalid libusb selector: {selector!r}") from exc
        if self.bus <= 0 or self.address <= 0:
            raise LibusbError(f"invalid libusb selector: {selector!r}")
        self.selector = selector
        self.timeout_ms = timeout_ms
        self._library = _load_library()
        self._context = ctypes.c_void_p()
        self._device = ctypes.c_void_p()
        self._config = ctypes.POINTER(_ConfigDescriptor)()
        self._endpoints: _EndpointPair | None = None
        self._claimed = False
        self._closed = False
        self._open()

    def _open(self) -> None:
        code = self._library.libusb_init(ctypes.byref(self._context))
        if code < 0:
            raise _error(code, "initialize libusb")
        devices = ctypes.POINTER(ctypes.c_void_p)()
        count = self._library.libusb_get_device_list(
            self._context, ctypes.byref(devices)
        )
        if count < 0:
            self._library.libusb_exit(self._context)
            self._context = ctypes.c_void_p()
            raise _error(count, "enumerate USB devices")
        found = None
        try:
            for index in range(count):
                device = devices[index]
                try:
                    _, bus, address = _get_descriptor(self._library, device)
                except LibusbError:
                    continue
                if bus == self.bus and address == self.address:
                    found = device
                    code = self._library.libusb_open(
                        device, ctypes.byref(self._device)
                    )
                    if code < 0:
                        raise _error(code, "open USB printer")
                    break
            if found is None:
                raise LibusbError(
                    f"USB printer {self.selector} is no longer connected"
                )
            code = self._library.libusb_get_active_config_descriptor(
                found, ctypes.byref(self._config)
            )
            if code < 0:
                raise _error(code, "read USB printer configuration")
            self._endpoints = self._find_printer_endpoints()
        finally:
            self._library.libusb_free_device_list(devices, 1)
        code = self._library.libusb_set_auto_detach_kernel_driver(
            self._device, 1
        )
        if code < 0 and code != -12:
            self.close()
            raise _error(code, "detach kernel USB printer driver")
        code = self._library.libusb_claim_interface(
            self._device, self._endpoints.interface
        )
        if code < 0:
            self.close()
            raise _error(code, "claim USB printer interface")
        self._claimed = True

    def _find_printer_endpoints(self) -> _EndpointPair:
        if not self._config:
            raise LibusbError("active USB configuration is unavailable")
        for interface_index in range(self._config.contents.bNumInterfaces):
            interface = self._config.contents.interface[interface_index]
            for alt_index in range(interface.num_altsetting):
                alternate = interface.altsetting[alt_index]
                if (
                    alternate.bInterfaceClass != 7
                    or alternate.bInterfaceProtocol != 2
                ):
                    continue
                bulk_in = None
                bulk_out = None
                for endpoint_index in range(alternate.bNumEndpoints):
                    endpoint = alternate.endpoint[endpoint_index]
                    if endpoint.bmAttributes & 0x03 != 0x02:
                        continue
                    if endpoint.bEndpointAddress & 0x80:
                        bulk_in = int(endpoint.bEndpointAddress)
                    else:
                        bulk_out = int(endpoint.bEndpointAddress)
                if bulk_in is not None and bulk_out is not None:
                    return _EndpointPair(
                        interface=int(alternate.bInterfaceNumber),
                        bulk_in=bulk_in,
                        bulk_out=bulk_out,
                    )
        raise LibusbError("USB printer endpoints were not found")

    def _bulk_transfer(
        self,
        endpoint: int,
        buffer: ctypes.Array,
        length: int,
        timeout_ms: int,
        operation: str,
    ) -> int:
        transferred = ctypes.c_int()
        code = self._library.libusb_bulk_transfer(
            self._device,
            endpoint,
            ctypes.byref(buffer),
            length,
            ctypes.byref(transferred),
            timeout_ms,
        )
        if code == -7:
            return -7
        if code < 0:
            raise _error(code, operation)
        return transferred.value

    def send(self, data: bytes) -> None:
        if not data:
            return
        view = memoryview(data)
        while view:
            buffer = ctypes.create_string_buffer(view.tobytes())
            written = self._bulk_transfer(
                self._endpoints.bulk_out,
                buffer,
                len(view),
                self.timeout_ms,
                "write to USB printer",
            )
            if written == -7:
                raise LibusbError("timed out writing to USB printer")
            if written <= 0:
                raise LibusbError("short write to USB printer")
            view = view[written:]

    def _read_once(self, timeout_ms: int) -> bytes:
        buffer = ctypes.create_string_buffer(65536)
        received = self._bulk_transfer(
            self._endpoints.bulk_in,
            buffer,
            len(buffer),
            timeout_ms,
            "read from USB printer",
        )
        if received == -7:
            return b""
        return buffer.raw[:received]

    def drain(self, idle: float = 0.05, limit: int = 65536) -> None:
        total = 0
        while total < limit:
            chunk = self._read_once(max(1, min(50, int(idle * 1000))))
            if not chunk:
                break
            total += len(chunk)

    def receive(
        self,
        timeout: float,
        idle: float,
        expected: tuple[str, ...] | list[str] = (),
    ) -> bytes:
        del expected  # PJL completion is decided by query_merged.
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()
        while time.monotonic() < deadline:
            remaining = max(0.001, deadline - time.monotonic())
            wait = min(idle, remaining)
            chunk = self._read_once(max(1, int(wait * 1000)))
            if not chunk:
                if chunks and time.monotonic() - last_data >= idle:
                    break
                continue
            chunks.append(chunk)
            last_data = time.monotonic()
        return b"".join(chunks)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if getattr(self, "_library", None) is None:
            return
        if getattr(self, "_device", None) and self._device:
            if self._claimed and self._endpoints is not None:
                self._library.libusb_release_interface(
                    self._device, self._endpoints.interface
                )
            self._library.libusb_close(self._device)
            self._device = ctypes.c_void_p()
        if self._config:
            self._library.libusb_free_config_descriptor(self._config)
            self._config = ctypes.POINTER(_ConfigDescriptor)()
        if self._context:
            self._library.libusb_exit(self._context)
            self._context = ctypes.c_void_p()
