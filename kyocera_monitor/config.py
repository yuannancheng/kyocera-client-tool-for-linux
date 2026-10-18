"""Read-only access to 147 interoperable printer configuration objects.

The table is based on observed Client Tool 1.4.11.2 interoperability behavior
and is kept in sync with
``docs/reverse-engineering/data/clienttool-config-oids.tsv`` by
``tests/test_config.py``.  This module only builds ``KGETOBJ`` requests and
never emits ``KSETOBJ`` or any device-reset command.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from .config_vendor_names import VENDOR_NAMES
from .pjl import Channel, normalize_command, query_merged, split_segments
from .snmp import (
    END_OF_MIB_VIEW,
    NO_SUCH_INSTANCE,
    NO_SUCH_OBJECT,
    SnmpClient,
    VarBind,
    format_value,
)

# (OID below the Kyocera enterprise root or absolute OID, type code, item id)
# The item id is the 1-based row number used by the configuration client.
CONFIG_OBJECTS: tuple[tuple[str, int, int], ...] = (
    ("43.5.1.1.23.1", 0, 1),
    ("43.5.1.1.34.1", 0, 2),
    ("43.5.1.1.35.1", 0, 3),
    ("42.5.1.1.43.1", 0, 4),
    ("42.5.9.1.3.2", 0, 5),
    ("43.8.1.1.11.1.1", 0, 6),
    ("1001.2.1.1.1.8.1", 0, 7),
    ("1001.2.1.1.1.9.1", 0, 8),
    ("43.8.1.1.4.1.1", 0, 9),
    ("1001.2.1.1.1.15.1", 0, 10),
    ("43.21.1.1.3.1.1", 0, 11),
    ("43.21.1.1.3.1.2", 0, 12),
    ("43.21.1.1.3.1.3", 0, 13),
    ("43.21.1.1.3.1.4", 0, 14),
    ("43.21.1.1.3.1.5", 0, 15),
    ("43.21.1.1.3.1.6", 0, 16),
    ("43.21.1.1.3.1.7", 0, 17),
    ("43.21.1.1.3.1.8", 0, 18),
    ("43.21.1.1.3.1.9", 0, 19),
    ("43.21.1.1.3.1.10", 0, 20),
    ("43.21.1.1.3.1.11", 0, 21),
    ("43.21.1.1.3.1.12", 0, 22),
    ("43.21.1.1.3.1.13", 0, 23),
    ("43.21.1.1.3.1.14", 0, 24),
    ("43.21.1.1.3.1.15", 0, 25),
    ("43.21.1.1.3.1.16", 0, 26),
    ("43.21.1.1.3.1.17", 0, 27),
    ("43.21.1.1.3.1.18", 0, 28),
    ("43.21.1.1.3.1.19", 0, 29),
    ("43.21.1.1.3.1.20", 0, 30),
    ("43.21.1.1.3.1.21", 0, 31),
    ("43.21.1.1.3.1.22", 0, 32),
    ("43.21.1.1.2.1.15", 5, 33),
    ("43.21.1.1.2.1.16", 5, 34),
    ("43.21.1.1.2.1.17", 5, 35),
    ("43.21.1.1.2.1.18", 5, 36),
    ("43.21.1.1.2.1.19", 5, 37),
    ("43.21.1.1.2.1.20", 5, 38),
    ("43.21.1.1.2.1.21", 5, 39),
    ("43.21.1.1.2.1.22", 5, 40),
    ("43.21.1.1.5.1.15", 0, 41),
    ("43.21.1.1.5.1.16", 0, 42),
    ("43.21.1.1.5.1.17", 0, 43),
    ("43.21.1.1.5.1.18", 0, 44),
    ("43.21.1.1.5.1.19", 0, 45),
    ("43.21.1.1.5.1.20", 0, 46),
    ("43.21.1.1.5.1.21", 0, 47),
    ("43.21.1.1.5.1.22", 0, 48),
    ("43.10.1.1.13.1.1", 0, 49),
    ("1001.2.1.1.1.14.1", 0, 50),
    ("42.5.1.1.13.1", 0, 51),
    ("43.5.1.1.22.1", 0, 52),
    ("42.5.1.1.50.1", 0, 53),
    ("40.10.1.1.5.1", 5, 54),
    ("42.5.9.1.3.1", 0, 55),
    ("40.10.1.1.1.1", 0, 56),
    ("40.10.1.1.2.1", 0, 57),
    ("40.1.1.1.9.1", 0, 58),
    ("40.10.1.1.4.1", 3, 59),
    ("40.10.1.1.6.1", 3, 60),
    ("40.10.1.1.7.1", 3, 61),
    ("40.20.1.1.1.1", 0, 62),
    ("40.21.1.1.1.1", 0, 63),
    ("40.36.1.1.1.1", 0, 64),
    ("40.26.2.1.3.1", 5, 65),
    ("40.26.2.1.4.1", 5, 66),
    ("1.3.6.1.2.1.1.4.0", 5, 67),
    ("1.3.6.1.2.1.1.5.0", 5, 68),
    ("1.3.6.1.2.1.1.6.0", 5, 69),
    ("1.3.6.1.2.1.11.30.0", 0, 70),
    ("40.26.5.1.7.1.1", 0, 71),
    ("40.26.5.1.4.1.1", 5, 72),
    ("40.26.5.1.2.1.1", 3, 73),
    ("40.26.5.1.5.1.1", 0, 74),
    ("40.26.5.1.7.1.2", 0, 75),
    ("40.26.5.1.4.1.2", 5, 76),
    ("40.26.5.1.2.1.2", 3, 77),
    ("40.26.5.1.5.1.2", 0, 78),
    ("1.3.6.1.2.1.43.5.1.1.10.1", 0, 79),
    ("1001.2.2.1.1.4.1", 0, 80),
    ("1001.2.2.1.1.5.1", 0, 81),
    ("1001.2.2.1.1.7.1", 0, 82),
    ("1001.2.1.1.1.10.1", 0, 83),
    ("42.5.1.1.4.1", 0, 84),
    ("42.5.1.1.5.1", 0, 85),
    ("42.5.1.1.3.1", 0, 86),
    ("46.8.1.1.6.3.1", 0, 87),
    ("46.8.1.1.12.3.1", 0, 88),
    ("46.8.1.1.13.3.1", 0, 89),
    ("1001.2.2.1.1.1.1", 0, 90),
    ("1001.2.2.1.1.2.1", 0, 91),
    ("1001.2.2.1.1.3.1", 0, 92),
    ("1001.2.2.1.1.8.1", 0, 93),
    ("1.3.6.1.2.1.43.7.1.1.3.1.1", 5, 94),
    ("1.3.6.1.2.1.43.7.1.1.3.1.2", 5, 95),
    ("1.3.6.1.2.1.43.7.1.1.3.1.3", 5, 96),
    ("1.3.6.1.2.1.43.7.1.1.3.1.4", 5, 97),
    ("1.3.6.1.2.1.43.7.1.1.3.1.5", 5, 98),
    ("1.3.6.1.2.1.43.7.1.1.3.1.6", 5, 99),
    ("1.3.6.1.2.1.43.7.1.1.3.1.7", 5, 100),
    ("1.3.6.1.2.1.43.7.1.1.3.1.8", 5, 101),
    ("1.3.6.1.2.1.43.7.1.1.3.1.9", 5, 102),
    ("1.3.6.1.2.1.43.7.1.1.3.1.10", 5, 103),
    ("1.3.6.1.2.1.43.7.1.1.3.1.11", 5, 104),
    ("1.3.6.1.2.1.43.7.1.1.3.1.12", 5, 105),
    ("1001.2.2.1.1.6.1", 0, 106),
    ("42.5.9.1.3.3", 0, 107),
    ("45.8.1.1.11.4", 0, 108),
    ("45.8.1.1.10.4", 0, 109),
    ("45.10.3.1.1.4", 0, 110),
    ("45.9.3.1.1.4", 0, 111),
    ("45.10.3.1.2.4", 0, 112),
    ("45.10.3.1.3.4", 0, 113),
    ("45.9.3.1.2.4", 0, 114),
    ("1001.2.3.1.1.1.1", 0, 115),
    ("45.9.1.1.4.4", 0, 116),
    ("45.8.1.1.6.4", 0, 117),
    ("45.8.1.1.4.4", 0, 118),
    ("45.5.1.1.3.4", 5, 119),
    ("45.5.1.1.2.4", 5, 120),
    ("45.8.1.1.1.4", 0, 121),
    ("45.8.1.1.7.4", 0, 122),
    ("45.8.1.1.3.4", 0, 123),
    ("45.8.1.1.9.4", 0, 124),
    ("45.9.1.1.2.4", 0, 125),
    ("45.8.1.1.2.4", 0, 126),
    ("45.8.1.1.17.4", 0, 127),
    ("45.10.2.1.1.1.4", 0, 128),
    ("45.10.2.1.1.5.4", 0, 129),
    ("45.10.2.2.1.1.4", 5, 130),
    ("45.10.2.2.1.2.4", 5, 131),
    ("45.10.2.1.1.2.4", 0, 132),
    ("45.10.2.5.1.1.4", 5, 133),
    ("45.10.1.1.1.3.4", 0, 134),
    ("45.10.2.5.1.9.4", 0, 135),
    ("45.10.2.5.1.8.4", 0, 136),
    ("45.8.1.1.16.4", 6, 137),
    ("45.8.2.1.10.4.1", 0, 138),
    ("45.8.2.1.11.4.1", 0, 139),
    ("45.8.2.1.12.4.1", 0, 140),
    ("45.8.2.1.13.4.1", 0, 141),
    ("40.42.1.1.1.1", 0, 142),
    ("40.42.1.1.3.1", 0, 143),
    ("40.42.1.1.4.1", 5, 144),
    ("40.42.1.1.5.1", 0, 145),
    ("40.42.1.1.7.1", 0, 146),
    ("40.42.1.1.6.1", 0, 147),
)

TYPE_NAMES = {0: "integer", 3: "ipv4", 5: "string", 6: "mac"}

# Only objects with independent evidence keep a business label here.  The
# remaining rows deliberately stay OID-only instead of guessing from position.
CONFIG_KNOWN: dict[str, dict[str, object]] = {
    "43.5.1.1.22.1": {
        "label": "Form feed timeout",
        "scale": 5,
        "unit": "s",
        "confidence": "verified",
    },
    "43.5.1.1.34.1": {
        "label": "Auto error clear",
        "choices": {0: "OFF", 1: "ON"},
        "confidence": "verified",
    },
    "43.5.1.1.35.1": {
        "label": "Auto error clear timeout",
        "scale": 5,
        "unit": "s",
        "confidence": "verified",
    },
    # The main KMUTLCFG dialog copies model[0..10] into its stack frame.
    # FUN_00405c10 then uses: item 1 for the 0x3f2 minute spinner, item 4 for
    # the 0x463 power-off combo, and item 50 for the 0x455 quiet-mode checkbox.
    # The values are device observations; no write-readback test exists yet.
    "43.5.1.1.23.1": {
        "label": "Sleep time",
        "unit": "min",
        "confidence": "inferred",
    },
    "42.5.1.1.43.1": {
        "label": "Power off timer",
        "confidence": "inferred",
    },
    "1001.2.1.1.1.14.1": {
        "label": "Quiet mode",
        "choices": {0: "OFF", 1: "ON"},
        "confidence": "inferred",
    },
    # Wi-Fi status page (KMUTLCFG dialog 0x00f3): each object is read
    # directly into the model slot that the page displays.  The enums come
    # from FUN_00403e80 and the English RT_STRING resources 0x204..0x20d.
    "40.42.1.1.1.1": {
        "label": "Wi-Fi connection state",
        "choices": {3: "Connected", 4: "Not connected"},
        "confidence": "verified",
    },
    "40.42.1.1.3.1": {
        "label": "Wi-Fi enable state",
        "confidence": "verified",
    },
    "40.42.1.1.4.1": {
        "label": "Wi-Fi SSID",
        "confidence": "verified",
    },
    "40.42.1.1.5.1": {
        "label": "Wi-Fi security mode",
        "choices": {
            0: "Open (Disable)",
            1: "Open (WEP)",
            2: "WPA2/WPA PSK (AES)",
            3: "WPA2/WPA PSK (Auto)",
            4: "WPA2 PSK (AES)",
        },
        "confidence": "verified",
    },
    "40.42.1.1.6.1": {
        "label": "Wi-Fi channel",
        "confidence": "verified",
    },
    "40.42.1.1.7.1": {
        "label": "Wi-Fi RSSI",
        "unit": "dBm",
        "confidence": "verified",
    },
    "40.10.1.1.4.1": {"label": "IPv4 address", "confidence": "verified"},
    "40.10.1.1.5.1": {"label": "Host name", "confidence": "verified"},
    "40.10.1.1.6.1": {"label": "Subnet mask", "confidence": "verified"},
    "40.10.1.1.7.1": {"label": "Default gateway", "confidence": "verified"},
    "40.26.2.1.3.1": {
        "label": "SNMP read community",
        "confidence": "verified",
    },
    "40.26.2.1.4.1": {
        "label": "SNMP write community",
        "confidence": "verified",
    },
    "43.21.1.1.2.1.15": {
        "label": "Custom paper 1 name",
        "confidence": "verified",
    },
    "43.21.1.1.3.1.15": {
        "label": "Custom paper 1 weight/type index",
        "confidence": "verified",
    },
}

# MA2000w returns the literal strings "Custom 2" .. "Custom 8" for these
# columns and "Custom 1" for row 33, so the names are device-verified.
for _paper in range(2, 9):
    CONFIG_KNOWN[f"43.21.1.1.2.1.{14 + _paper}"] = {
        "label": f"Custom paper {_paper} name",
        "confidence": "verified",
    }

_KGETOBJ_RE = re.compile(r'^@PJL KGETOBJ OBJ="([^"]+)"$', re.IGNORECASE)


@dataclass(frozen=True)
class ConfigObject:
    item_id: int
    oid: str
    type_code: int

    @property
    def pjl_object(self) -> str:
        if self.oid.startswith("1.3.6"):
            return f"#{self.oid}"
        return f"1.{self.oid}"

    @property
    def command(self) -> str:
        return f'@PJL KGETOBJ OBJ="{self.pjl_object}"'


CONFIG: tuple[ConfigObject, ...] = tuple(
    ConfigObject(item_id=item_id, oid=oid, type_code=type_code)
    for oid, type_code, item_id in CONFIG_OBJECTS
)


def build_config_commands() -> tuple[str, ...]:
    """Return the exact read-only KGETOBJ batch used by KMUTLCFG.exe."""
    return tuple(obj.command for obj in CONFIG)


def absolute_config_oid(oid: str) -> str:
    """Expand the ClientTool relative OID spelling to an absolute SNMP OID."""
    if oid.startswith("1.3.6"):
        return oid
    return f"1.3.6.1.4.1.1347.{oid}"


def _hex_text(value: str) -> bytes | None:
    compact = "".join(value.split())
    if not compact or len(compact) % 2:
        return None
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return None


def _octets_to_text(data: bytes) -> str | None:
    """Decode a fixed-length octet string, ignoring NUL padding."""
    data = data.rstrip(b"\0")
    if not data:
        return ""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if all(character.isprintable() or character in "\t\r\n" for character in text):
        return text
    return None


def decode_value(pjl_type: int | None, raw: str) -> tuple[object, str]:
    """Decode one PJL VALUE according to the response TYPE field."""
    if pjl_type == 2:
        try:
            return int(raw, 10), "integer"
        except ValueError:
            return raw, "text"
    if pjl_type == 64:
        text = raw.strip()
        decoded = _hex_text(text)
        if decoded is not None:
            printable = _octets_to_text(decoded)
            if printable:
                text = printable
        if re.fullmatch(r"[0-9A-Fa-f]{8}", text):
            octets = struct.unpack("!BBBB", bytes.fromhex(text))
            return ".".join(str(octet) for octet in octets), "ipv4"
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", text):
            return text, "ipv4"
        return raw, "text"
    if pjl_type == 4:
        decoded = _hex_text(raw)
        if decoded is None:
            return raw, "text"
        text = _octets_to_text(decoded)
        if text is not None:
            return text, "string"
        return decoded.hex(), "hex"
    if pjl_type == 0 or raw == "":
        return None, "empty"
    return raw, "text"


def decode_snmp_value(varbind: VarBind) -> tuple[object, str]:
    """Decode one SNMP varbind into the same shape as a PJL VALUE."""
    if varbind.tag in (NO_SUCH_OBJECT, NO_SUCH_INSTANCE, END_OF_MIB_VIEW):
        return None, "missing"
    if varbind.tag == 0x02:  # INTEGER
        return int(varbind.value), "integer"
    if varbind.tag == 0x40:  # IpAddress
        data = varbind.value
        if isinstance(data, bytes) and len(data) == 4:
            return ".".join(str(part) for part in data), "ipv4"
    if varbind.tag in (0x41, 0x42, 0x43, 0x46):  # counters/gauges/ticks
        return int(varbind.value), "integer"
    if varbind.tag == 0x04:  # OCTET STRING
        data = varbind.value
        if isinstance(data, bytes):
            text = _octets_to_text(data)
            if text is not None:
                return text, "string"
            return data.hex(), "hex"
    if varbind.tag == 0x01:  # BOOLEAN
        return int(varbind.value), "integer"
    return format_value(varbind.tag, varbind.value), "text"


def _display_value(value: object, known: dict[str, object] | None) -> object:
    display = value
    if isinstance(value, int) and known:
        choices = known.get("choices")
        if choices and value in choices:
            display = choices[value]
        scale = known.get("scale")
        if isinstance(scale, int):
            display = value * scale
        unit = known.get("unit")
        if unit:
            display = f"{display} {unit}"
    return display


def _parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key.strip().upper()] = value.strip().strip('"')
    return fields


def parse_config_response(data: bytes | str) -> list[dict]:
    """Parse a merged PJL response into one record per configuration object."""
    raw = data.encode("ascii", "replace") if isinstance(data, str) else data
    segments = split_segments(raw)
    records: list[dict] = []
    for obj in CONFIG:
        segment = segments.get(normalize_command(obj.command))
        record: dict[str, object] = {
            "item_id": obj.item_id,
            "oid": obj.oid,
            "pjl_object": obj.pjl_object,
            "source": "pjl",
            "vendor_name": VENDOR_NAMES.get(obj.oid),
            "value": None,
            "display": None,
        }
        known = CONFIG_KNOWN.get(obj.oid)
        if known:
            record.update(known)
        if segment is None:
            record["error"] = "missing response"
            records.append(record)
            continue
        text = segment.decode("ascii", "replace")
        first, _, body = text.partition("\n")
        if not _KGETOBJ_RE.match(first.strip().lstrip("\x0c")):
            record["error"] = "unexpected response"
            records.append(record)
            continue
        fields = _parse_fields(body)
        status_text = fields.get("STATUS")
        try:
            status = int(status_text) if status_text is not None else None
        except ValueError:
            status = None
        record["status"] = status
        record["pjl_type"] = (
            int(fields["TYPE"]) if fields.get("TYPE", "").isdigit() else None
        )
        record["raw_value"] = fields.get("VALUE", "")
        if status != 0:
            record["error"] = (
                f"STATUS={status_text}" if status_text is not None else "no STATUS"
            )
            records.append(record)
            continue
        value, kind = decode_value(record["pjl_type"], record["raw_value"])
        record["value"] = value
        record["value_kind"] = kind
        record["display"] = _display_value(value, known)
        records.append(record)
    return records


def collect_config(
    channel: Channel,
    *,
    timeout: float = 8.0,
    idle: float = 1.5,
) -> list[dict]:
    """Query all configuration objects over an already-open PJL channel."""
    response = query_merged(
        channel,
        build_config_commands(),
        timeout=timeout,
        idle=idle,
    )
    return parse_config_response(response)


def collect_config_snmp(
    host: str,
    *,
    community: str = "public",
    version: str = "2c",
    port: int = 161,
    timeout: float = 1.5,
    retries: int = 1,
    batch_size: int = 16,
    client: SnmpClient | None = None,
) -> list[dict]:
    """Read the same 147 objects over read-only SNMP, including while asleep."""
    client = client or SnmpClient(
        host,
        community=community,
        version=version,
        port=port,
        timeout=timeout,
        retries=retries,
    )
    oids = [absolute_config_oid(obj.oid) for obj in CONFIG]
    found: dict[str, VarBind] = {}
    for start in range(0, len(oids), batch_size):
        requested = oids[start : start + batch_size]
        for varbind in client.get(requested):
            found[varbind.oid] = varbind

    records: list[dict] = []
    for obj in CONFIG:
        absolute = absolute_config_oid(obj.oid)
        varbind = found.get(absolute)
        record: dict[str, object] = {
            "item_id": obj.item_id,
            "oid": obj.oid,
            "absolute_oid": absolute,
            "source": "snmp",
            "vendor_name": VENDOR_NAMES.get(obj.oid),
            "value": None,
            "display": None,
        }
        known = CONFIG_KNOWN.get(obj.oid)
        if known:
            record.update(known)
        if varbind is None:
            record["error"] = "no such object"
            records.append(record)
            continue
        value, kind = decode_snmp_value(varbind)
        if kind == "missing":
            record["error"] = varbind.type_name
            records.append(record)
            continue
        record["status"] = 0
        record["snmp_type"] = varbind.type_name
        record["raw_value"] = format_value(varbind.tag, varbind.value)
        record["value"] = value
        record["value_kind"] = kind
        record["display"] = _display_value(value, known)
        records.append(record)
    return records
