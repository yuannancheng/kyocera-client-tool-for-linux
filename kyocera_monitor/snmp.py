#!/usr/bin/env python3
"""Minimal SNMP v1/v2c client used for read-only device queries.

This deliberately depends only on the Python standard library so that protocol
experiments remain reproducible on a fresh Linux system.
"""

from __future__ import annotations

import argparse
import socket
import sys
from dataclasses import dataclass
from typing import Iterable


class BerError(ValueError):
    pass


def encode_length(length: int) -> bytes:
    if length < 0:
        raise BerError("negative length")
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def encode_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + encode_length(len(value)) + value


def encode_integer(value: int) -> bytes:
    if value == 0:
        raw = b"\x00"
    elif value > 0:
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        if raw[0] & 0x80:
            raw = b"\x00" + raw
    else:
        size = max(1, (value.bit_length() + 8) // 8)
        raw = value.to_bytes(size, "big", signed=True)
        while len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0x80:
            raw = raw[1:]
    return encode_tlv(0x02, raw)


def encode_oid(oid: str) -> bytes:
    parts = [p for p in oid.strip().strip(".").split(".") if p != ""]
    if len(parts) < 2:
        raise BerError(f"OID needs at least two components: {oid!r}")
    numbers = [int(p) for p in parts]
    if not 0 <= numbers[0] <= 2 or not 0 <= numbers[1] <= 39:
        raise BerError(f"invalid leading OID components: {oid!r}")

    body = bytearray([numbers[0] * 40 + numbers[1]])
    for number in numbers[2:]:
        if number < 0:
            raise BerError(f"negative OID component: {oid!r}")
        chunk = [number & 0x7F]
        number >>= 7
        while number:
            chunk.append(0x80 | (number & 0x7F))
            number >>= 7
        body.extend(reversed(chunk))
    return encode_tlv(0x06, bytes(body))


def decode_length(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise BerError("truncated length")
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    count = first & 0x7F
    if count == 0 or count > 4:
        raise BerError("unsupported BER length")
    if offset + count > len(data):
        raise BerError("truncated long length")
    return int.from_bytes(data[offset : offset + count], "big"), offset + count


def decode_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    if offset >= len(data):
        raise BerError("truncated tag")
    tag = data[offset]
    length, value_offset = decode_length(data, offset + 1)
    end = value_offset + length
    if end > len(data):
        raise BerError("truncated value")
    return tag, data[value_offset:end], end


def decode_integer(value: bytes) -> int:
    if not value:
        raise BerError("empty integer")
    return int.from_bytes(value, "big", signed=True)


def decode_oid(value: bytes) -> str:
    if not value:
        raise BerError("empty OID")
    first = value[0]
    numbers = [first // 40, first % 40]
    current = 0
    for byte in value[1:]:
        current = (current << 7) | (byte & 0x7F)
        if not byte & 0x80:
            numbers.append(current)
            current = 0
    if current:
        raise BerError("truncated OID component")
    return ".".join(str(n) for n in numbers)


NO_SUCH_OBJECT = 0x80
NO_SUCH_INSTANCE = 0x81
END_OF_MIB_VIEW = 0x82

VALUE_NAMES = {
    0x01: "Boolean",
    0x02: "Integer",
    0x03: "BitString",
    0x04: "OctetString",
    0x05: "Null",
    0x06: "ObjectIdentifier",
    0x40: "IpAddress",
    0x41: "Counter32",
    0x42: "Gauge32",
    0x43: "TimeTicks",
    0x44: "Opaque",
    0x46: "Counter64",
    NO_SUCH_OBJECT: "NoSuchObject",
    NO_SUCH_INSTANCE: "NoSuchInstance",
    END_OF_MIB_VIEW: "EndOfMibView",
}


def decode_value(tag: int, value: bytes) -> object:
    if tag == 0x02:
        return decode_integer(value)
    if tag in (0x04, 0x40):
        return value
    if tag == 0x06:
        return decode_oid(value)
    if tag in (0x41, 0x42, 0x43, 0x46):
        return int.from_bytes(value, "big")
    if tag == 0x05:
        return None
    if tag in (NO_SUCH_OBJECT, NO_SUCH_INSTANCE, END_OF_MIB_VIEW):
        return VALUE_NAMES[tag]
    return value


def format_value(tag: int, value: object) -> str:
    if isinstance(value, bytes):
        if tag == 0x40 and len(value) == 4:
            return ".".join(str(b) for b in value)
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return "0x" + value.hex()
        if all(32 <= ord(ch) < 127 or ch in "\r\n\t" for ch in text):
            return text.replace("\r", "\\r").replace("\n", "\\n")
        return "0x" + value.hex()
    return "null" if value is None else str(value)


@dataclass
class VarBind:
    oid: str
    tag: int
    value: object

    @property
    def type_name(self) -> str:
        return VALUE_NAMES.get(self.tag, f"Tag0x{self.tag:02x}")

    def __str__(self) -> str:
        return f"{self.oid} = {self.type_name}: {format_value(self.tag, self.value)}"


def encode_varbind(oid: str) -> bytes:
    return encode_tlv(0x30, encode_oid(oid) + encode_tlv(0x05, b""))


def build_request(
    version: int,
    community: str,
    pdu_tag: int,
    request_id: int,
    oids: Iterable[str],
    *,
    non_repeaters: int = 0,
    max_repetitions: int = 0,
) -> bytes:
    if pdu_tag == 0xA5:
        prefix = encode_integer(non_repeaters) + encode_integer(max_repetitions)
    else:
        prefix = (
            encode_integer(request_id)
            + encode_integer(0)
            + encode_integer(0)
        )
    varbinds = b"".join(encode_varbind(oid) for oid in oids)
    pdu = encode_tlv(pdu_tag, prefix + encode_tlv(0x30, varbinds))
    return encode_tlv(
        0x30,
        encode_integer(version)
        + encode_tlv(0x04, community.encode("utf-8"))
        + pdu,
    )


def parse_response(data: bytes) -> tuple[int, int, list[VarBind]]:
    tag, message, end = decode_tlv(data)
    if tag != 0x30 or end != len(data):
        raise BerError("unexpected SNMP message framing")

    offset = 0
    version_tag, version_raw, offset = decode_tlv(message, offset)
    if version_tag != 0x02:
        raise BerError("missing SNMP version")
    version = decode_integer(version_raw)

    community_tag, _, offset = decode_tlv(message, offset)
    if community_tag != 0x04:
        raise BerError("missing SNMP community")

    pdu_tag, pdu, offset = decode_tlv(message, offset)
    if offset != len(message):
        raise BerError("trailing SNMP message bytes")

    pdu_offset = 0
    for _ in range(2):
        _, _, pdu_offset = decode_tlv(pdu, pdu_offset)
    _, error_index_raw, pdu_offset = decode_tlv(pdu, pdu_offset)
    error_index = decode_integer(error_index_raw)

    list_tag, varbind_list, pdu_offset = decode_tlv(pdu, pdu_offset)
    if list_tag != 0x30 or pdu_offset != len(pdu):
        raise BerError("unexpected varbind list framing")

    varbinds: list[VarBind] = []
    offset = 0
    while offset < len(varbind_list):
        item_tag, item, offset = decode_tlv(varbind_list, offset)
        if item_tag != 0x30:
            raise BerError("unexpected varbind framing")
        oid_tag, oid_raw, item_offset = decode_tlv(item, 0)
        value_tag, value_raw, item_offset = decode_tlv(item, item_offset)
        if oid_tag != 0x06 or item_offset != len(item):
            raise BerError("unexpected varbind content")
        varbinds.append(
            VarBind(decode_oid(oid_raw), value_tag, decode_value(value_tag, value_raw))
        )

    return pdu_tag, error_index, varbinds


def exchange(host: str, port: int, packet: bytes, timeout: float, retries: int) -> bytes:
    address = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        last_error: OSError | None = None
        for _ in range(retries + 1):
            sock.sendto(packet, address)
            try:
                response, _ = sock.recvfrom(65535)
                return response
            except socket.timeout as exc:
                last_error = exc
        raise TimeoutError(f"no SNMP response from {host}:{port}") from last_error


def walk(
    host: str,
    port: int,
    community: str,
    version: int,
    oid: str,
    timeout: float,
    retries: int,
    max_rows: int,
    bulk: bool,
) -> list[VarBind]:
    rows: list[VarBind] = []
    current = oid
    request_id = 1
    root = oid.rstrip(".")
    while len(rows) < max_rows:
        if bulk:
            packet = build_request(
                version,
                community,
                0xA5,
                request_id,
                [current],
                non_repeaters=0,
                max_repetitions=min(20, max_rows - len(rows)),
            )
        else:
            packet = build_request(version, community, 0xA1, request_id, [current])
        response = exchange(host, port, packet, timeout, retries)
        _, error_index, varbinds = parse_response(response)
        if error_index:
            raise BerError(f"SNMP error-index {error_index} while walking {current}")
        if not varbinds:
            break
        progressed = False
        for varbind in varbinds:
            if varbind.tag == END_OF_MIB_VIEW:
                return rows
            if not varbind.oid.startswith(root + "."):
                return rows
            if varbind.oid == current:
                continue
            rows.append(varbind)
            current = varbind.oid
            progressed = True
            if len(rows) >= max_rows:
                break
        if not progressed:
            break
        request_id += 1
    return rows


def walk_columns(
    host: str,
    port: int,
    community: str,
    version: int,
    root: str,
    columns: Iterable[int | str],
    timeout: float,
    retries: int,
    max_rows: int,
) -> list[VarBind]:
    """Walk selected table columns with one GETNEXT request per row.

    A plain subtree walk costs one request per cell. Printer MIB tables have
    many columns per row, so asking for every needed column in the same
    GETNEXT request keeps the request count proportional to the row count.
    """
    root = root.rstrip(".")
    current = [f"{root}.{column}" for column in columns]
    rows: list[VarBind] = []
    request_id = 1
    root_parts = len(root.split("."))
    while current and len(rows) < max_rows:
        packet = build_request(version, community, 0xA1, request_id, current)
        request_id += 1
        response = exchange(host, port, packet, timeout, retries)
        _, error_index, varbinds = parse_response(response)
        if error_index:
            # SNMPv1 reports one bad column for the whole request; drop it and
            # keep walking the remaining columns.
            if 1 <= error_index <= len(current):
                current.pop(error_index - 1)
                continue
            raise BerError(f"SNMP error-index {error_index} while walking {root}")
        if not varbinds:
            break
        next_oids: list[str] = []
        for requested, varbind in zip(current, varbinds):
            if varbind.tag == END_OF_MIB_VIEW:
                continue
            parts = requested.split(".")
            if len(parts) <= root_parts:
                continue
            prefix = f"{root}.{parts[root_parts]}"
            if not varbind.oid.startswith(prefix + "."):
                # This column has no more instances.
                continue
            rows.append(varbind)
            next_oids.append(varbind.oid)
            if len(rows) >= max_rows:
                break
        if not next_oids or next_oids == current:
            break
        current = next_oids
    return rows


class SnmpClient:
    """Small synchronous SNMP client for scalar GETs and table walks."""

    def __init__(
        self,
        host: str,
        *,
        community: str = "public",
        version: str = "1",
        port: int = 161,
        timeout: float = 2.0,
        retries: int = 1,
    ):
        if version not in ("1", "2c"):
            raise ValueError(f"unsupported SNMP version: {version!r}")
        self.host = host
        self.community = community
        self.version = 0 if version == "1" else 1
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.request_id = 1

    def get(self, oids: Iterable[str], *, strict: bool = False) -> list[VarBind]:
        """GET several scalars, dropping unsupported OIDs when not strict.

        SNMPv1 rejects a whole request with ``noSuchName`` when one OID is not
        implemented, so the failing varbind is removed and the request retried.
        """
        remaining = list(oids)
        values: dict[str, VarBind] = {}
        for _ in range(len(remaining) + 1):
            if not remaining:
                break
            packet = build_request(
                self.version,
                self.community,
                0xA0,
                self.request_id,
                remaining,
            )
            self.request_id += 1
            response = exchange(
                self.host, self.port, packet, self.timeout, self.retries
            )
            _, error_index, varbinds = parse_response(response)
            if error_index:
                if strict:
                    raise BerError(f"SNMP error-index {error_index}")
                index = min(max(error_index, 1), len(remaining)) - 1
                remaining.pop(index)
                continue
            for varbind in varbinds:
                if varbind.tag in (
                    NO_SUCH_OBJECT,
                    NO_SUCH_INSTANCE,
                    END_OF_MIB_VIEW,
                ):
                    continue
                values[varbind.oid] = varbind
            break
        return list(values.values())

    def walk(self, root: str, *, max_rows: int = 200) -> list[VarBind]:
        return walk(
            self.host,
            self.port,
            self.community,
            self.version,
            root,
            self.timeout,
            self.retries,
            max_rows,
            bulk=False,
        )

    def walk_columns(
        self, root: str, columns: Iterable[int | str], *, max_rows: int = 200
    ) -> list[VarBind]:
        return walk_columns(
            self.host,
            self.port,
            self.community,
            self.version,
            root,
            columns,
            self.timeout,
            self.retries,
            max_rows,
        )

    def walk_rows(
        self,
        root: str,
        columns: Iterable[int | str],
        *,
        sentinel_column: int | str,
        max_rows: int = 200,
    ) -> list[VarBind]:
        """Read selected columns of a table row by row.

        One sentinel column enumerates the row instances with plain GETNEXT;
        the remaining columns are then fetched with one multi-OID GET per row.
        This avoids GETNEXT calls that cross a table boundary, which the
        MA2000w answers only after a multi-second delay.
        """
        root = root.rstrip(".")
        sentinel_root = f"{root}.{sentinel_column}"
        prefix = sentinel_root + "."
        instances = [
            varbind.oid[len(prefix) :]
            for varbind in self.walk(sentinel_root, max_rows=max_rows)
            if varbind.oid.startswith(prefix)
        ]
        rows: list[VarBind] = []
        for instance in instances:
            oids = [f"{root}.{column}.{instance}" for column in columns]
            rows.extend(self.get(oids))
        return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("get", "walk"))
    parser.add_argument("host")
    parser.add_argument("oids", nargs="+")
    parser.add_argument("--community", default="public")
    parser.add_argument(
        "--version",
        choices=("1", "2c"),
        default="1",
        help="SNMP version (default: 1; MA2000w ignores v2c GETBULK)",
    )
    parser.add_argument("--port", type=int, default=161)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=200)
    parser.add_argument(
        "--pdu",
        choices=("auto", "getnext", "getbulk"),
        default="auto",
        help="walk PDU; auto uses GETBULK for v2c and GETNEXT for v1",
    )
    args = parser.parse_args()

    version = 0 if args.version == "1" else 1
    bulk = args.pdu == "getbulk" or (args.pdu == "auto" and version == 1)
    if version == 0 and bulk:
        parser.error("SNMPv1 does not support GETBULK")
    try:
        if args.command == "get":
            packet = build_request(version, args.community, 0xA0, 1, args.oids)
            response = exchange(args.host, args.port, packet, args.timeout, args.retries)
            _, error_index, varbinds = parse_response(response)
            if error_index:
                print(f"SNMP error-index: {error_index}", file=sys.stderr)
                return 2
            for varbind in varbinds:
                print(varbind)
        else:
            for oid in args.oids:
                rows = walk(
                    args.host,
                    args.port,
                    args.community,
                    version,
                    oid,
                    args.timeout,
                    args.retries,
                    args.max_rows,
                    bulk=bulk,
                )
                for row in rows:
                    print(row)
    except (BerError, TimeoutError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
