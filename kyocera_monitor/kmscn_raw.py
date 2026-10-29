"""Decode the banded RAW container emitted by KM-WSDL scan sessions."""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_SIZE = 11
COLOR_PLANES = (2, 3, 4)


class RawScanError(ValueError):
    """Raised when a scan container does not match the recovered format."""


@dataclass(frozen=True)
class RawChunk:
    command: int
    subtype: int
    color: int
    width: int
    height: int
    data: bytes


@dataclass(frozen=True)
class DecodedScan:
    width: int
    height: int
    rgb: bytes
    chunks: tuple[RawChunk, ...]


def parse_chunks(data: bytes) -> tuple[RawChunk, ...]:
    """Split the raw stream using the lengths and 7-byte headers."""
    chunks: list[RawChunk] = []
    offset = 0
    while offset + HEADER_SIZE <= len(data):
        payload_length = int.from_bytes(data[offset : offset + 4], "big")
        if payload_length < 7:
            raise RawScanError(f"invalid chunk length at {offset}")
        end = offset + 4 + payload_length
        if end > len(data):
            raise RawScanError(f"truncated chunk at {offset}")
        header = data[offset + 4 : offset + HEADER_SIZE]
        chunks.append(
            RawChunk(
                command=header[0],
                subtype=header[1],
                color=header[2],
                width=int.from_bytes(header[3:5], "big"),
                height=int.from_bytes(header[5:7], "big"),
                data=data[offset + HEADER_SIZE : end],
            )
        )
        offset = end

    remaining = data[offset:]
    page_end_header = b"\x00\x00\x00\x04\x82\x82"
    if remaining and not (
        len(remaining) == 8 and remaining.startswith(page_end_header)
    ):
        raise RawScanError(f"unsupported trailing bytes: {remaining.hex()}")
    return tuple(chunks)


def _average_columns(chunk: RawChunk) -> bytes:
    expected = chunk.width * chunk.height
    if len(chunk.data) < expected:
        raise RawScanError(
            f"short calibration data for color {chunk.color}"
        )
    sums = [0] * chunk.width
    for row in range(chunk.height):
        start = row * chunk.width
        row_data = chunk.data[start : start + chunk.width]
        for column, value in enumerate(row_data):
            sums[column] += value
    return bytes(
        min(255, int(total / chunk.height + 0.5))
        for total in sums
    )


def _adjusted_pixel(
    raw: int,
    dark: int,
    white: int,
) -> int:
    doubled_white = white * 2
    if doubled_white - dark < 1:
        return 255
    numerator = raw * 2 - dark
    if numerator < 1:
        return 0
    return min(255, numerator * 255 // (doubled_white - dark))


def decode_raw(data: bytes) -> DecodedScan:
    """Decode raw scan bands into a top-down RGB raster."""
    chunks = parse_chunks(data)
    dark: dict[int, bytes] = {}
    white: dict[int, bytes] = {}
    bands: dict[int, list[RawChunk]] = {
        color: [] for color in COLOR_PLANES
    }

    for chunk in chunks:
        if chunk.color not in COLOR_PLANES:
            continue
        if chunk.command == 0x8A and chunk.subtype in {0x8A, 0x8B}:
            target = dark if chunk.subtype == 0x8A else white
            target[chunk.color] = _average_columns(chunk)
        elif chunk.command == 0x82 and chunk.subtype == 0x81:
            bands[chunk.color].append(chunk)

    if set(dark) != set(COLOR_PLANES) or set(white) != set(COLOR_PLANES):
        raise RawScanError("missing dark or white calibration band")
    if any(not bands[color] for color in COLOR_PLANES):
        raise RawScanError("missing one or more color planes")

    widths = {
        chunk.width
        for color in COLOR_PLANES
        for chunk in bands[color]
    }
    if len(widths) != 1:
        raise RawScanError("color planes use inconsistent widths")
    width = widths.pop()
    heights = {
        color: sum(chunk.height for chunk in bands[color])
        for color in COLOR_PLANES
    }
    if len(set(heights.values())) != 1:
        raise RawScanError("color planes use inconsistent heights")
    height = next(iter(heights.values()))

    planes: dict[int, bytearray] = {
        color: bytearray(width * height) for color in COLOR_PLANES
    }
    for color in COLOR_PLANES:
        correction = bytearray(width * 256)
        for column in range(width):
            base = column * 256
            for raw in range(256):
                correction[base + raw] = _adjusted_pixel(
                    raw,
                    dark[color][column],
                    white[color][column],
                )
        row_offset = 0
        for chunk in bands[color]:
            expected = chunk.width * chunk.height
            if len(chunk.data) < expected:
                raise RawScanError(
                    f"short band data for color {color}"
                )
            for row in range(chunk.height):
                source = row * chunk.width
                target = (row_offset + row) * width
                for column in range(width):
                    planes[color][target + column] = correction[
                        column * 256 + chunk.data[source + column]
                    ]
            row_offset += chunk.height

    rgb = bytearray(width * height * 3)
    for position in range(width * height):
        target = position * 3
        rgb[target] = planes[2][position]
        rgb[target + 1] = planes[3][position]
        rgb[target + 2] = planes[4][position]
    return DecodedScan(
        width=width,
        height=height,
        rgb=bytes(rgb),
        chunks=chunks,
    )


def encode_bmp(scan: DecodedScan) -> bytes:
    """Encode the decoded raster as an uncompressed 24-bit bottom-up BMP."""
    row_stride = (scan.width * 3 + 3) & ~3
    pixel_bytes = row_stride * scan.height
    file_size = 54 + pixel_bytes
    header = struct.pack(
        "<2sIHHI",
        b"BM",
        file_size,
        0,
        0,
        54,
    )
    dib = struct.pack(
        "<IiiHHIIiiII",
        40,
        scan.width,
        scan.height,
        1,
        24,
        0,
        pixel_bytes,
        2835,
        2835,
        0,
        0,
    )
    padding = b"\x00" * (row_stride - scan.width * 3)
    rows = bytearray()
    for row in range(scan.height - 1, -1, -1):
        for column in range(scan.width):
            base = (row * scan.width + column) * 3
            rows.append(scan.rgb[base + 2])
            rows.append(scan.rgb[base + 1])
            rows.append(scan.rgb[base])
        rows.extend(padding)
    return header + dib + bytes(rows)
