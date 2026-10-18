"""Parsers for PJL responses used by Kyocera printers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Codes the original monitor treats as non-warning in its INFO STATUS handler.
NORMAL_STATUS_CODES = frozenset({10001, 10002, 30014, 35078, 38001, 10036, 30001})
TONER_ALERT_CODES = frozenset({40038, 10023})

# Only objects whose meaning is confirmed by interoperability tests or by
# vendor-published identifiers are exposed as structured fields.
# All raw KGETOBJ values remain available in PrinterSnapshot.kgetobj.
KGETOBJ_KNOWN = {
    "1.46.10.1.1.5.3": {"field": "scan_count", "label": "Scan count"},
    "1.43.10.1.1.8.1.1": {"field": "drum_counter", "label": "Drum counter"},
    "1.43.10.1.1.14.1.1": {
        "field": "drum_counter_max",
        "label": "Drum counter max",
    },
    # The original program multiplies these raw values by five before showing
    # them (FUN_004258c0 in KMSTMNW.exe). The OID names below come from the
    # vendor's NetViewer snmp-oid.xml. KGETOBJ object paths use a protocol
    # prefix: ``1.`` maps to the Kyocera enterprise subtree
    # 1.3.6.1.4.1.1347, while ``2.`` maps to the Printer MIB subtree
    # 1.3.6.1.2.1.43. Both mappings are verified against device values.
    "2.5.1.1.10.1": {
        "field": "console_localization",
        "label": "Console localization",
        "confidence": "verified",
    },
    # kmPanelFirmwareVersion. MA2000w answers KGETOBJ with STATUS=2 and an
    # empty value, so this field remains available for other models only when
    # the device returns STATUS=0.
    "1.42.5.1.1.16.1": {
        "field": "panel_firmware_version",
        "label": "Panel firmware version",
    },
    "1.43.5.1.1.22.1": {
        "field": "form_feed_timeout",
        "label": "Form feed timeout",
        "scale": 5,
        "unit": "s",
    },
    "1.43.5.1.1.33.1": {
        "field": "sleep_mode",
        "label": "Sleep mode",
        "choices": {0: "OFF", 1: "ON"},
    },
    "1.43.5.1.1.34.1": {
        "field": "auto_error_clear",
        "label": "Auto error clear",
        "choices": {0: "OFF", 1: "ON"},
    },
    "1.43.5.1.1.35.1": {
        "field": "auto_error_clear_timeout",
        "label": "Auto error clear timeout",
        "scale": 5,
        "unit": "s",
    },
    # The resource DLL contains a "Lifetime counter" label and a "pages" unit.
    # The device returns the same value through standard SNMP
    # prtMarkerLifeCount (1.3.6.1.2.1.43.10.2.1.4.1.1), which verifies the
    # meaning even though the two protocols use different encodings.
    "2.10.2.1.4.1.1": {
        "field": "lifetime_counter",
        "label": "Lifetime counter",
        "unit": "pages",
        "confidence": "verified",
    },
}


@dataclass
class Tray:
    name: str
    status: str | None = None
    paper: str | None = None
    media: str | None = None
    remain: str | None = None
    capacity: str | None = None


@dataclass
class PrinterSnapshot:
    model: str | None = None
    serial: str | None = None
    firmware: str | None = None
    status_code: int | None = None
    display: str | None = None
    online: bool | None = None
    toner_level: int | None = None
    coverage: float | None = None
    engine_version: str | None = None
    timeout: int | None = None
    unit_name: str | None = None
    network: dict[str, str] = field(default_factory=dict)
    input_trays: list[Tray] = field(default_factory=list)
    tray_status: list[Tray] = field(default_factory=list)
    kgetobj: dict[str, dict[str, str]] = field(default_factory=dict)
    kgetobj_known: dict[str, dict[str, object]] = field(default_factory=dict)
    snmp: dict[str, object] = field(default_factory=dict)
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def normal(self) -> bool | None:
        if self.status_code is None and self.snmp.get("device_status") is not None:
            return self.snmp.get("device_status") == 2
        if self.status_code is None:
            return None
        return self.status_code in NORMAL_STATUS_CODES

    @property
    def toner_alert(self) -> bool:
        return self.status_code in TONER_ALERT_CODES

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "serial": self.serial,
            "firmware": self.firmware,
            "status_code": self.status_code,
            "display": self.display,
            "online": self.online,
            "normal": self.normal,
            "toner_level": self.toner_level,
            "coverage": self.coverage,
            "engine_version": self.engine_version,
            "timeout": self.timeout,
            "unit_name": self.unit_name,
            "network": self.network,
            "input_trays": [tray.__dict__ for tray in self.input_trays],
            "tray_status": [tray.__dict__ for tray in self.tray_status],
            "kgetobj": self.kgetobj,
            "kgetobj_known": self.kgetobj_known,
            "snmp": self.snmp,
        }


def split_sections(text: str) -> dict[str, str]:
    text = text.replace("\x1b%-12345X", "").replace("\x0c", "\n")
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("@PJL "):
            if current is not None:
                sections[current] = "\n".join(lines).strip("\n")
            current = line.strip()
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip("\n")
    return sections


def _quoted(body: str) -> str | None:
    match = re.search(r'"([^"]*)"', body)
    return match.group(1) if match else None


def _table_rows(body: str, prefix: str) -> list[list[str]]:
    rows = []
    for line in body.splitlines():
        if line.startswith(prefix):
            rows.append(line.split("\t")[1:])
    return rows


def _parse_config(snapshot: PrinterSnapshot, body: str) -> None:
    serial = re.search(r'SERIAL NUMBER="([^"]*)"', body)
    if serial:
        snapshot.serial = serial.group(1)
    firmware = re.search(r"FIRMWARE DATECODE=(.+)", body)
    if firmware:
        snapshot.firmware = firmware.group(1).strip()
    for row in _table_rows(body, "\tINTRAY"):
        if len(row) >= 4 and row[0] != "INTRAY":
            snapshot.input_trays.append(
                Tray(
                    name=row[0],
                    paper=row[2],
                    media=row[3],
                    capacity=row[4] if len(row) > 4 else None,
                )
            )


def _parse_kconfig(snapshot: PrinterSnapshot, body: str) -> None:
    toner = re.search(r"BLACK TONER LEVEL=(\d+)%", body)
    if toner:
        snapshot.toner_level = int(toner.group(1))
    coverage = re.search(r"BLACK COVERAGE=([0-9.]+)%", body)
    if coverage:
        snapshot.coverage = float(coverage.group(1))
    engine = re.search(r"ENGINE VERSION=(.+)", body)
    if engine:
        snapshot.engine_version = engine.group(1).strip()


def _parse_network(snapshot: PrinterSnapshot, body: str) -> None:
    rows = _table_rows(body, "\t")
    for row in rows:
        if len(row) >= 5 and row[0] in ("NET", "LAN", "WLAN"):
            snapshot.network = {
                "interface": row[0],
                "ip": row[1],
                "gateway": row[2],
                "subnet": row[3],
                "mac": row[4],
            }
            return


def _parse_tray_status(snapshot: PrinterSnapshot, body: str) -> None:
    for row in _table_rows(body, "\tINTRAY"):
        if len(row) >= 4 and row[0] != "INTRAY":
            snapshot.tray_status.append(
                Tray(
                    name=row[0],
                    status=row[1],
                    paper=row[2],
                    media=row[3],
                    remain=row[4] if len(row) > 4 else None,
                )
            )


def _parse_status(snapshot: PrinterSnapshot, body: str) -> None:
    code = re.search(r"CODE=(\d+)", body)
    if code:
        snapshot.status_code = int(code.group(1))
    display = re.search(r'DISPLAY="(.*)"', body, re.DOTALL)
    if display:
        snapshot.display = display.group(1).strip()
    online = re.search(r"ONLINE=(TRUE|FALSE)", body)
    if online:
        snapshot.online = online.group(1) == "TRUE"


def _parse_kgetobj(snapshot: PrinterSnapshot, command: str, body: str) -> None:
    oid = re.search(r'OBJ="([^"]+)"', command)
    values: dict[str, str] = {}
    for line in body.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip().strip('"')
    object_id = oid.group(1) if oid else command
    snapshot.kgetobj[object_id] = values

    known = KGETOBJ_KNOWN.get(object_id)
    if known and values.get("STATUS") == "0":
        raw_value = values.get("VALUE", "")
        if raw_value:
            try:
                value: object = int(raw_value)
            except ValueError:
                value = raw_value
            if isinstance(value, int):
                choices = known.get("choices")
                if choices and value in choices:
                    value = choices[value]
                scale = known.get("scale")
                if scale:
                    value = value * scale
            entry = {
                "object": object_id,
                "label": known["label"],
                "value": value,
                "type": values.get("TYPE"),
            }
            if known.get("unit"):
                entry["unit"] = known["unit"]
            if known.get("confidence"):
                entry["confidence"] = known["confidence"]
            snapshot.kgetobj_known[known["field"]] = entry


def parse_response(data: bytes | str) -> PrinterSnapshot:
    if isinstance(data, bytes):
        text = data.decode("ascii", "replace")
    else:
        text = data
    sections = split_sections(text)
    snapshot = PrinterSnapshot(sections=sections)

    for command, body in sections.items():
        if command == "@PJL INFO ID":
            snapshot.model = _quoted(body)
        elif command == "@PJL INFO CONFIG":
            _parse_config(snapshot, body)
        elif command == "@PJL INFO KCONFIG":
            _parse_kconfig(snapshot, body)
        elif command == "@PJL INFO KNETWORKSTATUS":
            _parse_network(snapshot, body)
        elif command == "@PJL INFO KINTRAYSTATUS":
            _parse_tray_status(snapshot, body)
        elif command == "@PJL INFO STATUS":
            _parse_status(snapshot, body)
        elif command == "@PJL INQUIRE TIMEOUT":
            timeout = re.search(r"\d+", body)
            if timeout:
                snapshot.timeout = int(timeout.group(0))
        elif command == "@PJL INFO KUNITNAME":
            snapshot.unit_name = _quoted(body)
        elif command.startswith("@PJL KGETOBJ"):
            _parse_kgetobj(snapshot, command, body)

    return snapshot
