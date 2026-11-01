"""Integrated KM-WSDL scanning and local image export.

The device-facing scan format and the file format presented to the user are
separate concerns.  This module requests the validated RAW stream, applies the
recovered Kyocera decoder, and emits standard-library-only PNG, PDF, BMP, or
RAW output.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import secrets
import tempfile
import threading
import time
import zlib
from zipfile import ZIP_DEFLATED, ZipFile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from . import kmscn, kmscn_raw

ProgressCallback = Callable[[str, str], None]
LOCAL_OUTPUT_FORMATS = (
    "png",
    "pdf",
    "jpeg",
    "tiff",
    "high_compression_pdf",
    "xps",
    "bmp",
    "raw",
)
_TERMINAL_STATES = {"succeeded", "failed"}


class ScanError(RuntimeError):
    """A scan failure tied to one actionable workflow stage."""

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        response: kmscn.ScanResponse | None = None,
    ):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.response = response

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "stage": self.stage,
            "error": self.message,
        }
        if self.response is not None:
            payload["response"] = response_metadata(self.response)
        return payload


@dataclass(frozen=True)
class ScanOptions:
    color: str | None = None
    resolution: str | None = None
    original_image: str | None = None
    duplex_mode: str | None = None
    original_placement: str | None = None
    continuous_scan_mode: str | None = None
    output_format: str = "png"
    max_pages: int = 1
    max_polls: int = 60
    poll_interval: float = 1.0
    timeout: float = 30.0
    insecure: bool = False
    max_response_bytes: int = 64 * 1024 * 1024
    https: bool = False
    port: int | None = None
    device_file_format: str = "RAW"
    operation_id: str | None = None
    retrieve_only: bool = False

    def __post_init__(self) -> None:
        if self.color is not None and self.color not in kmscn.COLOR_SELECTIONS:
            raise ValueError(f"unsupported color selection: {self.color}")
        if (
            self.resolution is not None
            and self.resolution not in kmscn.SCAN_RESOLUTIONS
        ):
            raise ValueError(f"unsupported resolution: {self.resolution}")
        if (
            self.original_image is not None
            and self.original_image not in kmscn.ORIGINAL_IMAGES
        ):
            raise ValueError(f"unsupported original image: {self.original_image}")
        if (
            self.duplex_mode is not None
            and self.duplex_mode not in kmscn.DUPLEX_MODES
        ):
            raise ValueError(f"unsupported duplex mode: {self.duplex_mode}")
        if (
            self.original_placement is not None
            and self.original_placement not in kmscn.ORIGINAL_PLACEMENTS
        ):
            raise ValueError(
                f"unsupported original placement: {self.original_placement}"
            )
        if (
            self.continuous_scan_mode is not None
            and self.continuous_scan_mode not in kmscn.CONTINUOUS_SCAN_MODES
        ):
            raise ValueError(
                "unsupported continuous scan mode: "
                f"{self.continuous_scan_mode}"
            )
        if self.device_file_format not in kmscn.IMAGE_FILE_FORMATS:
            raise ValueError(
                f"unsupported device image format: {self.device_file_format}"
            )
        if self.output_format not in LOCAL_OUTPUT_FORMATS:
            raise ValueError(
                f"unsupported local output format: {self.output_format}"
            )
        if not 1 <= self.max_pages <= 10:
            raise ValueError("max_pages must be between 1 and 10")
        if not 1 <= self.max_polls <= 600:
            raise ValueError("max_polls must be between 1 and 600")
        if not 0 <= self.poll_interval <= 30:
            raise ValueError("poll_interval must be between 0 and 30 seconds")
        if not 0 < self.timeout <= 120:
            raise ValueError("timeout must be between 0 and 120 seconds")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if self.port is not None and not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.retrieve_only and self.operation_id is None:
            raise ValueError("retrieve_only requires operation_id")

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ScanOptions":
        """Build options from the small JSON object accepted by the Web API."""

        def optional_text(name: str) -> str | None:
            value = payload.get(name)
            if value in (None, ""):
                return None
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string or null")
            return value

        def integer(name: str, default: int) -> int:
            value = payload.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            return value

        output_format = payload.get("output_format", "png")
        if not isinstance(output_format, str):
            raise ValueError("output_format must be a string")
        return cls(
            color=optional_text("color"),
            resolution=optional_text("resolution"),
            original_image=optional_text("original_image"),
            output_format=output_format.lower(),
            max_pages=integer("max_pages", 1),
        )


@dataclass(frozen=True)
class ScanArtifact:
    filename: str
    media_type: str
    kind: str
    width: int | None
    height: int | None
    data: bytes = repr(False)

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def metadata(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "media_type": self.media_type,
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "bytes": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ScanResult:
    device: str
    endpoint: str
    operation_id: str
    pages: int
    requested_device_format: str | None
    effective_device_format: str | None
    outputs: tuple[ScanArtifact, ...]
    close_result: str | None
    close_error: str | None

    def metadata(self) -> dict[str, object]:
        return {
            "device": self.device,
            "endpoint": self.endpoint,
            "operation_id": self.operation_id,
            "pages": self.pages,
            "requested_device_format": self.requested_device_format,
            "effective_device_format": self.effective_device_format,
            "outputs": [output.metadata() for output in self.outputs],
            "close_result": self.close_result,
            "close_error": self.close_error,
        }


class ScanProtocol(Protocol):
    def build_endpoint(
        self, target: str, https: bool, port: int | None
    ) -> tuple[str, str]: ...

    def preflight(self, endpoint: str, **kwargs) -> kmscn.PreflightResult: ...

    def probe_default_configuration(
        self, endpoint: str, **kwargs
    ) -> kmscn.DefaultConfigurationResult: ...

    def set_configuration_value(
        self, node: kmscn.XmlNode, name: str, value: str
    ) -> kmscn.XmlNode: ...

    def configuration_value(
        self, node: kmscn.XmlNode, name: str
    ) -> str | None: ...

    def open_session(self, endpoint: str, **kwargs) -> kmscn.ScanResponse: ...

    def start_scan(
        self, endpoint: str, operation_id: str, configuration: kmscn.XmlNode, **kwargs
    ) -> kmscn.ScanResponse: ...

    def retrieve_image(
        self, endpoint: str, operation_id: str, **kwargs
    ) -> kmscn.ScanResponse: ...

    def close_session(
        self, endpoint: str, operation_id: str, **kwargs
    ) -> kmscn.ScanResponse: ...


def response_metadata(response: kmscn.ScanResponse) -> dict[str, object]:
    return {
        "operation": response.operation,
        "http_status": response.http_status,
        "result": response.result,
        "operation_id": response.operation_id,
        "file_type": response.file_type,
        "file_size": response.file_size,
        "content_type": response.content_type,
        "body_length": response.body_length,
        "fault_code": response.fault_code,
        "fault_reason": response.fault_reason,
    }


def _emit(progress: ProgressCallback | None, stage: str, message: str) -> None:
    if progress is not None:
        progress(stage, message)


def _response_error(response: kmscn.ScanResponse) -> str:
    if response.fault_reason:
        return f"{response.fault_code or 'SOAP fault'}: {response.fault_reason}"
    if response.result and response.result not in {"0", "SUCCESS"}:
        return f"device returned {response.result}"
    return f"HTTP {response.http_status}"


def decode_image_data(value: str | None) -> bytes:
    """Decode an inline base64 image, preserving the legacy text fallback."""
    if value is None:
        return b""
    compact = "".join(value.split())
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return value.encode("utf-8")


def png_chunk(name: bytes, data: bytes) -> bytes:
    return (
        len(data).to_bytes(4, "big")
        + name
        + data
        + (zlib.crc32(name + data) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def encode_png(scan: kmscn_raw.DecodedScan) -> bytes:
    """Encode the top-down RGB raster as a standards-compliant PNG."""
    if len(scan.rgb) != scan.width * scan.height * 3:
        raise ValueError("RGB raster length does not match image dimensions")
    compressor = zlib.compressobj(level=6)
    compressed: list[bytes] = []
    row_bytes = scan.width * 3
    for row in range(scan.height):
        start = row * row_bytes
        compressed.append(compressor.compress(b"\x00" + scan.rgb[start : start + row_bytes]))
    compressed.append(compressor.flush())
    ihdr = (
        scan.width.to_bytes(4, "big")
        + scan.height.to_bytes(4, "big")
        + bytes((8, 2, 0, 0, 0))
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", b"".join(compressed))
        + png_chunk(b"IEND", b"")
    )


def _pillow_image(scan: kmscn_raw.DecodedScan):
    try:
        from PIL import Image
    except ImportError as error:
        raise ValueError(
            "JPEG, TIFF, and XPS export require Pillow; "
            "install the kyocera-monitor package dependencies"
        ) from error
    return Image.frombytes("RGB", (scan.width, scan.height), scan.rgb)


def encode_jpeg(
    scan: kmscn_raw.DecodedScan,
    *,
    quality: int = 90,
    dpi: int = 300,
) -> bytes:
    """Encode one decoded page as a baseline RGB JPEG."""
    if not 1 <= quality <= 100:
        raise ValueError("JPEG quality must be between 1 and 100")
    output = io.BytesIO()
    with _pillow_image(scan) as image:
        image.save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
            dpi=(dpi, dpi),
        )
    return output.getvalue()


def encode_tiff(
    scans: list[kmscn_raw.DecodedScan],
    *,
    dpi: int = 300,
) -> bytes:
    """Encode one or more pages as a deflate-compressed TIFF."""
    if not scans:
        raise ValueError("at least one decoded page is required")
    images = [_pillow_image(scan) for scan in scans]
    output = io.BytesIO()
    try:
        images[0].save(
            output,
            format="TIFF",
            save_all=True,
            append_images=images[1:],
            compression="tiff_deflate",
            dpi=(dpi, dpi),
        )
    finally:
        for image in images:
            image.close()
    return output.getvalue()


def resolution_dpi(resolution: str | None) -> int:
    if not resolution:
        return 300
    match = resolution.rsplit("_", 1)[-1].split("X", 1)
    try:
        return max(1, int(match[0]))
    except (IndexError, ValueError):
        return 300


def _pdf_object(number: int, body: bytes) -> tuple[int, bytes]:
    return number, f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"


def encode_pdf(
    scans: list[kmscn_raw.DecodedScan],
    *,
    dpi: int = 300,
    high_compression: bool = False,
    jpeg_quality: int = 65,
) -> bytes:
    """Encode one image-only multipage PDF.

    The standard variant uses lossless Flate-compressed RGB.  The high
    compression variant embeds baseline JPEG streams with ``DCTDecode``.
    """
    if not scans:
        raise ValueError("at least one decoded page is required")
    dpi = max(1, dpi)
    page_count = len(scans)
    catalog_id = 1
    pages_id = 2
    first_page_id = 3
    page_ids = [first_page_id + index * 3 for index in range(page_count)]
    objects: list[tuple[int, bytes]] = []
    objects.append(
        _pdf_object(
            catalog_id,
            b"<< /Type /Catalog /Pages 2 0 R >>",
        )
    )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(
        _pdf_object(
            pages_id,
            f"<< /Type /Pages /Count {page_count} /Kids [{kids}] >>".encode(
                "ascii"
            ),
        )
    )

    for index, scan in enumerate(scans):
        page_id = page_ids[index]
        content_id = page_id + 1
        image_id = page_id + 2
        width_points = scan.width * 72 / dpi
        height_points = scan.height * 72 / dpi
        content = (
            f"q\n{width_points:.4f} 0 0 {height_points:.4f} 0 0 cm\n"
            "/Im0 Do\nQ\n"
        ).encode("ascii")
        objects.append(
            _pdf_object(
                page_id,
                (
                    f"<< /Type /Page /Parent {pages_id} 0 R "
                    f"/MediaBox [0 0 {width_points:.4f} {height_points:.4f}] "
                    f"/Resources << /XObject << /Im0 {image_id} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii"),
            )
        )
        objects.append(
            _pdf_object(
                content_id,
                (
                    f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
                    + content
                    + b"endstream"
                ),
            )
        )
        if high_compression:
            compressed = encode_jpeg(
                scan,
                quality=jpeg_quality,
                dpi=dpi,
            )
            image_filter = b"/Filter /DCTDecode "
        else:
            compressed = zlib.compress(scan.rgb, 6)
            image_filter = b"/Filter /FlateDecode "
        objects.append(
            _pdf_object(
                image_id,
                (
                    f"<< /Type /XObject /Subtype /Image /Width {scan.width} "
                    f"/Height {scan.height} /ColorSpace /DeviceRGB "
                    f"/BitsPerComponent 8 "
                    f"/Length {len(compressed)} >>\nstream\n"
                ).encode("ascii").replace(
                    b"/Length ",
                    image_filter + b"/Length ",
                    1,
                )
                + compressed
                + b"\nendstream",
            )
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for _, body in objects:
        offsets.append(len(output))
        output.extend(body)
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def encode_xps(
    scans: list[kmscn_raw.DecodedScan],
    *,
    dpi: int = 300,
    jpeg_quality: int = 90,
) -> bytes:
    """Encode pages as a self-contained Microsoft XPS package."""
    if not scans:
        raise ValueError("at least one decoded page is required")
    dpi = max(1, dpi)
    package_ns = "http://schemas.microsoft.com/xps/2005/06"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    content_types = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types">'
        '<Default Extension="rels" ContentType="application/vnd.'
        'openxmlformats-package.relationships+xml"/>'
        '<Default Extension="fdseq" ContentType="application/vnd.ms-package.'
        'xps-fixeddocumentsequence+xml"/>'
        '<Default Extension="fdoc" ContentType="application/vnd.ms-package.'
        'xps-fixeddocument+xml"/>'
        '<Default Extension="fpage" ContentType="application/vnd.ms-package.'
        'xps-fixedpage+xml"/>'
        '<Default Extension="jpg" ContentType="image/jpeg"/>'
        "</Types>"
    )
    root_relationships = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Relationships xmlns="{rel_ns}">'
        '<Relationship Type="http://schemas.microsoft.com/xps/2005/06/'
        'fixedrepresentation" Target="/FixedDocumentSequence.fdseq" '
        'Id="R0"/>'
        "</Relationships>"
    )
    document_sequence = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<FixedDocumentSequence xmlns="{package_ns}">'
        '<DocumentReference Source="/Documents/1/FixedDocument.fdoc"/>'
        "</FixedDocumentSequence>"
    )
    page_references = "".join(
        f'<PageContent Source="/Documents/1/Pages/{index}.fpage"/>'
        for index in range(1, len(scans) + 1)
    )
    fixed_document = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<FixedDocument xmlns="{package_ns}">'
        f"{page_references}</FixedDocument>"
    )

    output = io.BytesIO()
    with ZipFile(
        output, "w", compression=ZIP_DEFLATED, compresslevel=6
    ) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr(
            "FixedDocumentSequence.fdseq", document_sequence
        )
        archive.writestr("Documents/1/FixedDocument.fdoc", fixed_document)
        for index, scan in enumerate(scans, start=1):
            width = round(scan.width * 96 / dpi)
            height = round(scan.height * 96 / dpi)
            page = (
                '<?xml version="1.0" encoding="utf-8"?>'
                f'<FixedPage xmlns="{package_ns}" '
                'xmlns:xml="http://www.w3.org/XML/1998/namespace" '
                f'xml:lang="en-US" Width="{width}" Height="{height}">'
                f'<Path Data="M0,0 L{width},0 L{width},{height} '
                f'L0,{height} Z"><Path.Fill><ImageBrush '
                f'ImageSource="/Resources/Images/{index}.jpg" '
                f'Viewbox="0,0,{scan.width},{scan.height}" '
                'ViewboxUnits="Absolute" '
                f'Viewport="0,0,{width},{height}" '
                'ViewportUnits="Absolute" TileMode="None"/>'
                "</Path.Fill></Path></FixedPage>"
            )
            page_relationships = (
                '<?xml version="1.0" encoding="utf-8"?>'
                f'<Relationships xmlns="{rel_ns}">'
                '<Relationship Type="http://schemas.microsoft.com/xps/'
                '2005/06/image" '
                f'Target="../../Resources/Images/{index}.jpg" Id="R1"/>'
                "</Relationships>"
            )
            archive.writestr(f"Documents/1/Pages/{index}.fpage", page)
            archive.writestr(
                f"Documents/1/Pages/_rels/{index}.fpage.rels",
                page_relationships,
            )
            archive.writestr(
                f"Resources/Images/{index}.jpg",
                encode_jpeg(scan, quality=jpeg_quality, dpi=dpi),
            )
    return output.getvalue()


def export_pages(
    decoded_pages: list[kmscn_raw.DecodedScan],
    *,
    raw_pages: list[bytes],
    output_format: str,
    output_stem: str,
    resolution: str | None,
) -> tuple[ScanArtifact, ...]:
    """Generate user-facing files without changing device wire semantics."""
    dpi = resolution_dpi(resolution)
    if output_format in {"pdf", "high_compression_pdf"}:
        if len(decoded_pages) != len(raw_pages):
            raise ValueError("PDF export requires a decoded RAW page")
        data = encode_pdf(
            decoded_pages,
            dpi=dpi,
            high_compression=output_format == "high_compression_pdf",
        )
        first = decoded_pages[0]
        return (
            ScanArtifact(
                filename=f"{output_stem}.pdf",
                media_type="application/pdf",
                kind=output_format,
                width=first.width,
                height=first.height,
                data=data,
            ),
        )
    if output_format == "tiff":
        if len(decoded_pages) != len(raw_pages):
            raise ValueError("TIFF export requires a decoded RAW page")
        first = decoded_pages[0]
        return (
            ScanArtifact(
                filename=f"{output_stem}.tiff",
                media_type="image/tiff",
                kind="tiff",
                width=first.width,
                height=first.height,
                data=encode_tiff(decoded_pages, dpi=dpi),
            ),
        )
    if output_format == "xps":
        if len(decoded_pages) != len(raw_pages):
            raise ValueError("XPS export requires a decoded RAW page")
        first = decoded_pages[0]
        return (
            ScanArtifact(
                filename=f"{output_stem}.xps",
                media_type="application/vnd.ms-xpsdocument",
                kind="xps",
                width=first.width,
                height=first.height,
                data=encode_xps(decoded_pages, dpi=dpi),
            ),
        )
    outputs: list[ScanArtifact] = []
    for index, raw in enumerate(raw_pages, start=1):
        suffix = f"-{index}" if len(raw_pages) > 1 else ""
        if output_format == "raw":
            outputs.append(
                ScanArtifact(
                    filename=f"{output_stem}{suffix}.raw",
                    media_type="application/octet-stream",
                    kind="raw",
                    width=None,
                    height=None,
                    data=raw,
                )
            )
            continue
        decoded = decoded_pages[index - 1]
        if output_format == "png":
            data = encode_png(decoded)
            media_type = "image/png"
        elif output_format == "jpeg":
            data = encode_jpeg(decoded, dpi=dpi)
            media_type = "image/jpeg"
        elif output_format == "bmp":
            data = kmscn_raw.encode_bmp(decoded)
            media_type = "image/bmp"
        else:
            raise ValueError(f"unsupported local output format: {output_format}")
        extension = "jpg" if output_format == "jpeg" else output_format
        outputs.append(
            ScanArtifact(
                filename=f"{output_stem}{suffix}.{extension}",
                media_type=media_type,
                kind=output_format,
                width=decoded.width,
                height=decoded.height,
                data=data,
            )
        )
    return tuple(outputs)


def write_outputs(
    result: ScanResult,
    destination: Path,
) -> tuple[Path, ...]:
    """Atomically write scan artifacts and return their final paths."""
    paths: list[Path] = []
    for index, artifact in enumerate(result.outputs, start=1):
        if len(result.outputs) == 1:
            target = destination
        elif destination.suffix:
            target = destination.with_name(
                f"{destination.stem}-{index}{destination.suffix}"
            )
        else:
            target = destination / artifact.filename
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            dir=target.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(artifact.data)
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        paths.append(target)
    return tuple(paths)


def scan_device(
    device: str,
    options: ScanOptions,
    *,
    progress: ProgressCallback | None = None,
    protocol: ScanProtocol = kmscn,
    sleep: Callable[[float], None] = time.sleep,
) -> ScanResult:
    """Run the validated scan workflow and return local exported artifacts."""
    _, endpoint = protocol.build_endpoint(device, options.https, options.port)
    request_options = {
        "timeout": options.timeout,
        "insecure": options.insecure,
    }
    _emit(progress, "preflight", "正在检查扫描服务")
    preflight = protocol.preflight(endpoint, **request_options)
    if not preflight.ok:
        raise ScanError(
            "preflight",
            preflight.error or f"扫描预检失败: {preflight.failed_stage}",
        )

    _emit(progress, "default_configuration", "正在读取设备默认扫描配置")
    defaults = protocol.probe_default_configuration(endpoint, **request_options)
    if not defaults.ok or defaults.configuration is None:
        raise ScanError(
            "default_configuration",
            "设备没有返回可用的默认扫描配置",
        )
    configuration = defaults.configuration
    for field, value in (
        ("image_file_format", options.device_file_format),
        ("color_selection", options.color),
        ("scan_resolution", options.resolution),
        ("original_image", options.original_image),
        ("duplex_mode", options.duplex_mode),
        ("original_placement", options.original_placement),
        ("continuous_scan_mode", options.continuous_scan_mode),
    ):
        if value is not None:
            configuration = protocol.set_configuration_value(
                configuration, field, value
            )
    effective_format = protocol.configuration_value(
        configuration, "image_file_format"
    )

    if options.operation_id is not None:
        operation_id = options.operation_id
    else:
        _emit(progress, "open_session", "正在打开扫描会话")
        opened = protocol.open_session(endpoint, **request_options)
        if not opened.ok or opened.operation_id is None:
            raise ScanError(
                "open_session",
                _response_error(opened),
                response=opened,
            )
        operation_id = opened.operation_id
    decoded_pages: list[kmscn_raw.DecodedScan] = []
    raw_pages: list[bytes] = []
    completed = False
    close_result: str | None = None
    close_error: str | None = None
    try:
        if not options.retrieve_only:
            _emit(progress, "start_scan", "正在启动扫描")
            started = protocol.start_scan(
                endpoint,
                operation_id,
                configuration,
                **request_options,
            )
            if not started.ok:
                raise ScanError(
                    "start_scan",
                    _response_error(started),
                    response=started,
                )

        for poll in range(1, options.max_polls + 1):
            _emit(
                progress,
                "retrieve_image",
                f"正在等待第 {min(len(raw_pages) + 1, options.max_pages)} 页"
                f"（第 {poll} 次查询）",
            )
            retrieved = protocol.retrieve_image(
                endpoint,
                operation_id,
                max_response_bytes=options.max_response_bytes,
                **request_options,
            )
            if not retrieved.ok:
                raise ScanError(
                    "retrieve_image",
                    _response_error(retrieved),
                    response=retrieved,
                )
            if retrieved.result == "ALL_GET_COMPLETE":
                completed = True
                break
            if retrieved.result in {"IMAGE_CREATING_NOW", "CONTINUE_SCAN"}:
                sleep(options.poll_interval)
                continue
            data = decode_image_data(retrieved.image_data)
            if not data and retrieved.body is not None:
                data = retrieved.body
            if not data:
                raise ScanError(
                    "retrieve_image",
                    "设备报告图像成功，但没有返回图像数据",
                    response=retrieved,
                )
            if len(raw_pages) >= options.max_pages:
                sleep(options.poll_interval)
                continue

            received_format = (retrieved.file_type or effective_format or "").upper()
            if options.output_format != "raw" and received_format != "RAW":
                raise ScanError(
                    "decode_raw",
                    f"设备返回 {received_format or '未知格式'}，"
                    f"当前不能转换为本地 {options.output_format.upper()}",
                    response=retrieved,
                )
            raw_pages.append(data)
            if options.output_format != "raw":
                _emit(
                    progress,
                    "decode_raw",
                    f"正在解码第 {len(raw_pages)} 页 RAW 图像",
                )
                try:
                    decoded_pages.append(kmscn_raw.decode_raw(data))
                except ValueError as error:
                    raise ScanError(
                        "decode_raw",
                        str(error),
                        response=retrieved,
                    ) from error
            sleep(options.poll_interval)
        if not completed:
            raise ScanError(
                "retrieve_image",
                f"扫描在 {options.max_polls} 次查询后仍未完成",
            )
        if not raw_pages:
            raise ScanError("retrieve_image", "扫描完成但没有收到图像")
    finally:
        _emit(progress, "close_session", "正在关闭扫描会话")
        try:
            closed = protocol.close_session(
                endpoint,
                operation_id,
                **request_options,
            )
            close_result = closed.result
            if not closed.ok:
                close_error = _response_error(closed)
        except Exception as error:  # preserve the primary scan error
            close_error = f"{type(error).__name__}: {error}"

    _emit(progress, "export", "正在生成本地文件")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_stem = f"kyocera-scan-{timestamp}-{secrets.token_hex(2)}"
    try:
        outputs = export_pages(
            decoded_pages,
            raw_pages=raw_pages,
            output_format=options.output_format,
            output_stem=output_stem,
            resolution=options.resolution,
        )
    except ValueError as error:
        raise ScanError("export", str(error)) from error
    _emit(progress, "complete", "扫描完成")
    return ScanResult(
        device=device,
        endpoint=endpoint,
        operation_id=operation_id,
        pages=len(raw_pages),
        requested_device_format=options.device_file_format,
        effective_device_format=effective_format,
        outputs=outputs,
        close_result=close_result,
        close_error=close_error,
    )


@dataclass
class ScanJob:
    job_id: str
    device: str
    options: ScanOptions
    state: str
    stage: str
    message: str
    created_at: float
    updated_at: float
    result: ScanResult | None = None
    error: ScanError | None = None

    def metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "job_id": self.job_id,
            "device": self.device,
            "state": self.state,
            "stage": self.stage,
            "message": self.message,
            "output_format": self.options.output_format,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": None,
            "result": None,
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        if self.result is not None:
            payload["result"] = self.result.metadata()
        return payload


class ScanBusyError(RuntimeError):
    """Raised when the selected device already has an active scan."""


class ScanJobManager:
    """Run scans in worker threads with per-device busy protection."""

    def __init__(
        self,
        runner: Callable[..., ScanResult] = scan_device,
        *,
        max_jobs: int = 10,
        clock: Callable[[], float] = time.time,
    ):
        self._runner = runner
        self._max_jobs = max(1, max_jobs)
        self._clock = clock
        self._lock = threading.Lock()
        self._jobs: dict[str, ScanJob] = {}
        self._active_devices: set[str] = set()

    def start(self, device: str, options: ScanOptions) -> ScanJob:
        with self._lock:
            self._prune_locked()
            if device in self._active_devices:
                raise ScanBusyError(f"{device} 正在扫描")
            now = self._clock()
            job = ScanJob(
                job_id=secrets.token_hex(16),
                device=device,
                options=options,
                state="queued",
                stage="queued",
                message="扫描任务已排队",
                created_at=now,
                updated_at=now,
            )
            self._jobs[job.job_id] = job
            self._active_devices.add(device)
        thread = threading.Thread(
            target=self._run,
            args=(job,),
            name=f"kyocera-scan-{job.job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return job

    def _run(self, job: ScanJob) -> None:
        def progress(stage: str, message: str) -> None:
            with self._lock:
                job.state = "running"
                job.stage = stage
                job.message = message
                job.updated_at = self._clock()

        try:
            result = self._runner(job.device, job.options, progress=progress)
        except ScanError as error:
            with self._lock:
                job.state = "failed"
                job.stage = error.stage
                job.message = error.message
                job.error = error
                job.updated_at = self._clock()
        except Exception as error:
            wrapped = ScanError(
                "unexpected",
                f"{type(error).__name__}: {error}",
            )
            with self._lock:
                job.state = "failed"
                job.stage = wrapped.stage
                job.message = wrapped.message
                job.error = wrapped
                job.updated_at = self._clock()
        else:
            with self._lock:
                job.state = "succeeded"
                job.stage = "complete"
                job.message = "扫描完成"
                job.result = result
                job.updated_at = self._clock()
        finally:
            with self._lock:
                self._active_devices.discard(job.device)

    def _prune_locked(self) -> None:
        completed = [
            job
            for job in self._jobs.values()
            if job.state in _TERMINAL_STATES
        ]
        completed.sort(key=lambda job: job.updated_at)
        while len(self._jobs) >= self._max_jobs and completed:
            oldest = completed.pop(0)
            self._jobs.pop(oldest.job_id, None)

    def get(self, job_id: str) -> ScanJob:
        with self._lock:
            return self._jobs[job_id]

    def metadata(self, job_id: str) -> dict[str, object]:
        with self._lock:
            return self._jobs[job_id].metadata()

    def output(self, job_id: str, index: int) -> ScanArtifact:
        with self._lock:
            job = self._jobs[job_id]
            if job.result is None:
                raise KeyError((job_id, index))
            return job.result.outputs[index]

    def wait(self, job_id: str, timeout: float = 10.0) -> ScanJob:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get(job_id)
            if job.state in _TERMINAL_STATES:
                return job
            time.sleep(0.01)
        raise TimeoutError(f"scan job {job_id} did not finish")
