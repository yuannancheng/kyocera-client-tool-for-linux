"""Linux transport for KYOCERA vendor-specific USB scanner requests.

KMUSBSCN3 opens the Windows ``usbscan.sys`` device and sends control requests
through ``IOCTL_SEND_USB_REQUEST``.  The same control requests and bulk framing
can be issued directly with libusb on Linux.  This module implements the
verified connection, machine-information and version handshake, plus the
statically recovered ScanReq/ACK/PageData/JobEnd protocol. Image retrieval is
not exposed until its response stream is verified on hardware.
"""

from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass

from .usb_libusb import (
    LibusbError,
    _ConfigDescriptor,
    _EndpointPair,
    _get_descriptor,
    _load_library,
)


class UsbScanError(RuntimeError):
    pass


CONNECT_REQUEST = 0x41
DISCONNECT_REQUEST = 0x42
MACHINE_INFO_REQUEST = 0x21
VERSION_REQUEST = 0x22
SCAN_REQUEST = 0x81
PAGE_DATA_REQUEST = 0x82
JOB_END_REQUEST = 0x83

MACHINE_INFO_PACKET = b"\x00\x00\x00\x02\x21\x00"
MA2000W_MODEL_CODE = b"001"

ORIGINAL_SIZE_LABELS = {
    0: "AUTO",
    1: "LETTER",
    2: "LEGAL",
    3: "STATEMENT",
    4: "A4",
    5: "A5",
    6: "A6",
    7: "B5",
    8: "B6",
    9: "FOLIO",
    10: "OFICIOII",
    11: "EXECUTIVE",
    12: "ENVELOPE#10",
    13: "ENVELOPE#9",
    14: "ENVELOPEMONARCH",
    15: "ENVELOPE#6",
    16: "ENVELOPEC5",
    17: "ENVELOPEDL",
    18: "HAGAKI",
    19: "OUFUKUHAGAKI",
    20: "YOUKEI2",
    21: "YOUKEI4",
    22: "CUSTOM",
    23: "16K",
    24: "ISOB5",
    25: "MEXICAN_OFICIO",
    26: "LEDGER",
    27: "B4",
    28: "8K",
    29: "COMPUTER FORM",
    30: "A3",
}

FEED_METHOD_LABELS = {
    1: "AUTO",
    2: "DP",
    3: "TABLE",
}

RESOLUTION_LABELS = {
    200: "200X200",
    300: "300X300",
    400: "400X400",
    600: "600X600",
}

COLOR_MODE_LABELS = {
    1: "MONO",
    2: "GRAY",
    3: "COLOR",
}

ORIGINAL_IMAGE_LABELS = {
    1: "TEXT",
    2: "PHOTO",
    3: "TEXT+PHOTO",
    4: "OCR",
}

DENSITY_LABELS = {
    -3: "-3",
    -2: "-2",
    -1: "-1",
    0: "0",
    1: "1",
    2: "2",
    3: "3",
}

PAGE_MODE_LABELS = {
    1: "CNT",
    2: "STEP",
}

SHARPEN_LABELS = {
    0: "None",
    1: "Low",
    2: "Medium",
    3: "High",
}

DUPLEX_LABELS = {
    0: "SIMPLEX",
    1: "DUPLEX",
}

DUPLEX_EDGE_LABELS = {
    0: "LEFTRIGHT",
    1: "TOP",
}


@dataclass(frozen=True)
class UsbScanParameters:
    """The 20-DWORD scan structure passed to the official USB front end.

    DWORD slots 2, 8, 10 and 12 are retained even though the recovered ScanReq
    serializer does not emit them directly. Their semantics remain unconfirmed.
    """

    original_size: int = 4
    feed_method: int = 1
    unmodeled_slot_2: int = 0
    resolution: int = 300
    color_mode: int = 3
    original_image: int = 3
    density: int = 0
    reverse_image: int = 0
    unmodeled_slot_8: int = 0
    orientation: int = 4
    unmodeled_slot_10: int = 0
    page_mode: int = 1
    unmodeled_slot_12: int = 0
    scan_area: tuple[int, int, int, int] = (0, 0, 0, 0)
    duplex: int = 0
    duplex_edge: int = 0
    sharpen: int = 1


@dataclass(frozen=True)
class UsbScanAck:
    status: int
    result: str
    source: str | None
    retryable: bool = False


@dataclass(frozen=True)
class UsbScanPage:
    raw: bytes
    terminator: str
    scan_ack: UsbScanAck
    job_end_response: bytes


def build_version_request(model_code: bytes = MA2000W_MODEL_CODE) -> bytes:
    if len(model_code) != 3:
        raise ValueError("KYOCERA model code must contain three bytes")
    body = (
        bytes((VERSION_REQUEST, 0, 10))
        + model_code
        + b"\n"
    )
    return len(body).to_bytes(4, "big") + body


def parse_packet(raw: bytes) -> tuple[int, bytes]:
    if len(raw) < 6:
        raise UsbScanError("short USB scanner response")
    length = int.from_bytes(raw[:4], "big")
    end = 4 + length
    if length < 2 or end > len(raw):
        raise UsbScanError("invalid USB scanner response length")
    return raw[4], raw[6:end]


def _label(
    labels: dict[int, str],
    value: int,
    field: str,
) -> str:
    try:
        return labels[value]
    except KeyError as exc:
        raise UsbScanError(
            f"unsupported USB scan {field} value: {value}"
        ) from exc


def build_scan_request(parameters: UsbScanParameters | None = None) -> bytes:
    """Build the official ScanReq payload from the recovered 20-DWORD struct.

    The final two lines preserve the official serializer's observed format
    argument and trailing literal exactly. Do not normalize that layout until a
    device capture proves the printer accepts a replacement.
    """

    parameters = parameters or UsbScanParameters()
    if len(parameters.scan_area) != 4:
        raise ValueError("scan_area must contain four integers")
    left, top, right, bottom = parameters.scan_area
    size = _label(
        ORIGINAL_SIZE_LABELS,
        parameters.original_size,
        "original-size",
    )
    feed = _label(
        FEED_METHOD_LABELS,
        parameters.feed_method,
        "feed-method",
    )
    resolution = _label(
        RESOLUTION_LABELS,
        parameters.resolution,
        "resolution",
    )
    color = _label(
        COLOR_MODE_LABELS,
        parameters.color_mode,
        "color-mode",
    )
    image = _label(
        ORIGINAL_IMAGE_LABELS,
        parameters.original_image,
        "original-image",
    )
    density = _label(
        DENSITY_LABELS,
        parameters.density,
        "density",
    )
    page_mode = _label(
        PAGE_MODE_LABELS,
        parameters.page_mode,
        "page-mode",
    )
    sharpen = _label(
        SHARPEN_LABELS,
        parameters.sharpen,
        "sharpen",
    )

    body = f"\nR={size}"
    if parameters.orientation in (1, 4):
        body += "Y"
    body += (
        f"\nX={resolution}"
        f"\nM={color}"
        f"\nQ={image}"
        f"\nD={density}\n"
    )
    if parameters.reverse_image != -1:
        reverse = _label(
            {0: "OFF", 1: "ON"},
            parameters.reverse_image,
            "reverse-image",
        )
        body += f"U={reverse}\n"
    body += (
        f"F={feed}\n"
        f"P={page_mode}\n"
        f"S={sharpen}\n"
    )
    if parameters.duplex != -1:
        body += "B=" + _label(
            DUPLEX_LABELS,
            parameters.duplex,
            "duplex",
        ) + "\n"
    if parameters.duplex_edge != -1:
        body += "N=" + _label(
            DUPLEX_EDGE_LABELS,
            parameters.duplex_edge,
            "duplex-edge",
        ) + "\n"
    if parameters.orientation != -1:
        orientation = (
            "Top Edge Top"
            if parameters.orientation in (1, 3)
            else "Top Edge Left"
        )
        body += f"O={orientation}\n"
    area = "OFF" if (left, top, right, bottom) == (0, 0, 0, 0) else "ON"
    # The official path resolves this format pointer to "d,%d,%d,%d".
    body += f"E={area}\nA=d,{left},{top},{right}\n%d,%d,%d,%d"
    packet = bytearray(b"\x00" * 6 + body.encode("ascii"))
    packet[:4] = (len(packet) - 4).to_bytes(4, "big")
    packet[4] = SCAN_REQUEST
    packet[5] = 0
    return bytes(packet)


def parse_scan_ack(raw: bytes) -> UsbScanAck:
    """Parse the six-byte bulk response to ScanReq."""

    if len(raw) != 6:
        raise UsbScanError("USB ScanReq acknowledgement must be six bytes")
    command, _body = parse_packet(raw)
    if command != SCAN_REQUEST:
        raise UsbScanError(
            f"unexpected USB ScanReq acknowledgement 0x{command:02x}"
        )
    status = raw[5]
    mapping = {
        0x80: UsbScanAck(status, "success", None),
        0x8A: UsbScanAck(status, "ready", "platen"),
        0x8B: UsbScanAck(status, "ready", "document_processor"),
        0x81: UsbScanAck(status, "retry", None, retryable=True),
        0x82: UsbScanAck(status, "no_original", None),
    }
    return mapping.get(
        status,
        UsbScanAck(status, f"unknown_0x{status:02x}", None),
    )


def _consume_scan_frame(buffer: bytearray) -> tuple[bytes, int, int] | None:
    """Return one complete USB scan frame, or None when more bytes are needed."""

    if len(buffer) < 4:
        return None
    length = int.from_bytes(buffer[:4], "big")
    if length < 2:
        raise UsbScanError(f"invalid USB scan frame length: {length}")
    total = 4 + length
    if len(buffer) < total:
        return None
    frame = bytes(buffer[:total])
    del buffer[:total]
    return frame, frame[4], frame[5]


def parse_control_response(
    raw: bytes,
    *,
    request: int,
    success_codes: tuple[int, ...],
) -> bytes:
    command, _body = parse_packet(raw)
    if command != request:
        raise UsbScanError(
            f"unexpected USB scanner response 0x{command:02x} "
            f"for request 0x{request:02x}"
        )
    if len(raw) < 6:
        raise UsbScanError("short USB scanner control response")
    code = raw[5]
    if code not in success_codes:
        raise UsbScanError(
            f"USB scanner request 0x{request:02x} rejected: 0x{code:02x}"
        )
    return raw


def parse_machine_info(raw: bytes) -> dict[str, object]:
    command, body = parse_packet(raw)
    if command != MACHINE_INFO_REQUEST:
        raise UsbScanError(
            f"unexpected machine-info command 0x{command:02x}"
        )
    text = body.decode("ascii", "replace").strip()
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            values[name] = value
    return {"raw": values}


def parse_version(raw: bytes) -> int:
    command, body = parse_packet(raw)
    if command != VERSION_REQUEST:
        raise UsbScanError(f"unexpected version command 0x{command:02x}")
    text = body.decode("ascii", "replace").strip()
    try:
        return int(text)
    except ValueError as exc:
        raise UsbScanError(f"invalid version value: {text!r}") from exc


@dataclass
class UsbScannerControl:
    vendor_id: int = 0x0482
    product_id: int = 0x0D51
    timeout_ms: int = 15000

    def __post_init__(self) -> None:
        self._library = None
        self._context = ctypes.c_void_p()
        self._device = ctypes.c_void_p()
        self._config = ctypes.POINTER(_ConfigDescriptor)()
        self._endpoints: _EndpointPair | None = None
        self._interface = 0
        self._claimed = False
        self._connected = False

    def __enter__(self) -> "UsbScannerControl":
        try:
            self.open()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()

    def open(self) -> None:
        library = _load_library()
        library.libusb_control_transfer.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint16,
            ctypes.c_uint16,
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.c_uint,
        ]
        library.libusb_control_transfer.restype = ctypes.c_int
        self._library = library
        context = ctypes.c_void_p()
        code = library.libusb_init(ctypes.byref(context))
        if code < 0:
            raise UsbScanError(f"libusb initialization failed: {code}")
        self._context = context
        devices = ctypes.POINTER(ctypes.c_void_p)()
        count = library.libusb_get_device_list(context, ctypes.byref(devices))
        if count < 0:
            raise UsbScanError(f"libusb enumeration failed: {count}")
        found = None
        try:
            for index in range(count):
                device = devices[index]
                descriptor, _bus, _address = _get_descriptor(library, device)
                if (
                    descriptor.idVendor == self.vendor_id
                    and descriptor.idProduct == self.product_id
                ):
                    found = device
                    code = library.libusb_open(
                        device, ctypes.byref(self._device)
                    )
                    if code < 0:
                        raise UsbScanError(f"cannot open USB scanner: {code}")
                    break
            if found is None:
                raise UsbScanError("MA2000w USB scanner was not found")
            code = library.libusb_get_active_config_descriptor(
                found, ctypes.byref(self._config)
            )
            if code < 0:
                raise UsbScanError(
                    f"cannot read USB scanner configuration: {code}"
                )
            self._find_vendor_interface()
        finally:
            library.libusb_free_device_list(devices, 1)

        code = library.libusb_set_auto_detach_kernel_driver(self._device, 1)
        if code < 0 and code != -12:
            raise UsbScanError(f"cannot detach USB scanner driver: {code}")
        code = library.libusb_claim_interface(
            self._device, self._interface
        )
        if code < 0:
            raise UsbScanError(f"cannot claim USB scanner interface: {code}")
        self._claimed = True

    def _find_vendor_interface(self) -> None:
        for index in range(self._config.contents.bNumInterfaces):
            interface = self._config.contents.interface[index]
            for alt_index in range(interface.num_altsetting):
                alternate = interface.altsetting[alt_index]
                if alternate.bInterfaceClass != 0xFF:
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
                    self._interface = int(alternate.bInterfaceNumber)
                    self._endpoints = _EndpointPair(
                        interface=self._interface,
                        bulk_in=bulk_in,
                        bulk_out=bulk_out,
                    )
                    return
        raise UsbScanError("vendor-specific USB scanner interface not found")

    def control_in(self, request: int, length: int = 255) -> bytes:
        buffer = ctypes.create_string_buffer(length)
        result = self._library.libusb_control_transfer(
            self._device,
            0xC0,
            request,
            0,
            self._interface,
            buffer,
            length,
            self.timeout_ms,
        )
        if result < 0:
            raise UsbScanError(
                f"USB scanner control request 0x{request:02x} failed: {result}"
            )
        return buffer.raw[:result]

    def bulk_out(self, data: bytes) -> None:
        buffer = ctypes.create_string_buffer(data)
        transferred = ctypes.c_int()
        result = self._library.libusb_bulk_transfer(
            self._device,
            self._endpoints.bulk_out,
            ctypes.byref(buffer),
            len(data),
            ctypes.byref(transferred),
            self.timeout_ms,
        )
        if result < 0:
            raise UsbScanError(f"USB scanner write failed: {result}")
        if transferred.value != len(data):
            raise UsbScanError("short write to USB scanner")

    def bulk_in(
        self,
        length: int = 128,
        *,
        timeout_ms: int | None = None,
    ) -> bytes:
        buffer = ctypes.create_string_buffer(length)
        transferred = ctypes.c_int()
        result = self._library.libusb_bulk_transfer(
            self._device,
            self._endpoints.bulk_in,
            ctypes.byref(buffer),
            length,
            ctypes.byref(transferred),
            self.timeout_ms if timeout_ms is None else timeout_ms,
        )
        if result < 0:
            raise UsbScanError(f"USB scanner read failed: {result}")
        return buffer.raw[: transferred.value]

    def connect(self) -> bytes:
        response = parse_control_response(
            self.control_in(CONNECT_REQUEST),
            request=CONNECT_REQUEST,
            success_codes=(0x80, 0x81, 0x82),
        )
        self._connected = True
        return response

    def machine_info(self) -> dict[str, object]:
        self.bulk_out(MACHINE_INFO_PACKET)
        return parse_machine_info(self.bulk_in())

    def version(self, model_code: bytes = MA2000W_MODEL_CODE) -> int:
        self.bulk_out(build_version_request(model_code))
        return parse_version(self.bulk_in())

    def start_scan(
        self,
        parameters: UsbScanParameters | None = None,
    ) -> UsbScanAck:
        """Submit the recovered ScanReq and parse its six-byte acknowledgement."""

        self.bulk_out(build_scan_request(parameters))
        ack = parse_scan_ack(self.bulk_in(6))
        if ack.result not in {"success", "ready"}:
            raise UsbScanError(
                "USB ScanReq was not accepted: "
                f"{ack.result} (0x{ack.status:02x})"
            )
        return ack

    def page_data(self) -> bytes:
        response = self.control_in(PAGE_DATA_REQUEST)
        command, _body = parse_packet(response)
        if command != PAGE_DATA_REQUEST:
            raise UsbScanError(
                f"unexpected USB page-data response 0x{command:02x}"
            )
        return response

    def end_job(self) -> bytes:
        return parse_control_response(
            self.control_in(JOB_END_REQUEST),
            request=JOB_END_REQUEST,
            success_codes=(0x80,),
        )

    def capture_page(
        self,
        parameters: UsbScanParameters | None = None,
        *,
        max_bytes: int = 64 * 1024 * 1024,
        max_seconds: float = 60.0,
        read_size: int = 256 * 1024,
    ) -> UsbScanPage:
        """Collect one recovered USB RAW page and close the scanner job.

        This method implements the statically recovered request order, but the
        complete stream has not yet been validated against the MA2000w.
        """

        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if max_seconds <= 0:
            raise ValueError("max_seconds must be positive")
        if read_size < 6:
            raise ValueError("read_size must be at least six bytes")

        ack = self.start_scan(parameters)
        self.page_data()
        buffer = bytearray()
        image_frames = bytearray()
        received = 0
        deadline = time.monotonic() + max_seconds
        terminator: str | None = None
        while terminator is None:
            if time.monotonic() >= deadline:
                raise UsbScanError("timed out waiting for USB scan page end")
            chunk = self.bulk_in(read_size)
            if not chunk:
                continue
            received += len(chunk)
            if received > max_bytes:
                raise UsbScanError("USB scan exceeded the maximum byte count")
            buffer.extend(chunk)
            while True:
                parsed = _consume_scan_frame(buffer)
                if parsed is None:
                    break
                frame, command, status = parsed
                if command == 0x7E and status == 0x7E:
                    terminator = "page"
                    break
                if command == 0x7E and status == 0x83:
                    terminator = "job"
                    break
                if command == 0x82 and status == 0x84:
                    continue
                if len(frame) >= 11 and command in {0x8A, 0x82}:
                    image_frames.extend(frame)

        job_end_response = b""
        if terminator == "page":
            job_end_response = self.end_job()
        return UsbScanPage(
            raw=bytes(image_frames),
            terminator=terminator,
            scan_ack=ack,
            job_end_response=job_end_response,
        )

    def disconnect(self) -> bytes:
        response = parse_control_response(
            self.control_in(DISCONNECT_REQUEST),
            request=DISCONNECT_REQUEST,
            success_codes=(0x80,),
        )
        self._connected = False
        return response

    def close(self) -> None:
        if self._library is None:
            return
        if self._connected:
            try:
                self.disconnect()
            except UsbScanError:
                pass
        if self._device:
            if self._claimed and self._endpoints is not None:
                self._library.libusb_release_interface(
                    self._device, self._interface
                )
            self._library.libusb_close(self._device)
            self._device = ctypes.c_void_p()
        if self._config:
            self._library.libusb_free_config_descriptor(self._config)
            self._config = ctypes.POINTER(_ConfigDescriptor)()
        if self._context:
            self._library.libusb_exit(self._context)
            self._context = ctypes.c_void_p()
        self._library = None
        self._claimed = False


def probe_scanner() -> dict[str, object]:
    with UsbScannerControl() as scanner:
        connect_response = scanner.connect()
        machine = scanner.machine_info()
        version = scanner.version()
        disconnect_response = scanner.disconnect()
        scanner._connected = False
    return {
        "vendor_id": "0482",
        "product_id": "0d51",
        "connect_response": connect_response.hex(),
        "machine_info": machine,
        "model_code": MA2000W_MODEL_CODE.decode("ascii"),
        "version": version,
        "disconnect_response": disconnect_response.hex(),
        "image_capture": "not_implemented",
    }
