"""Map read-only SNMP values to a :class:`PrinterSnapshot`.

The OIDs below are the ones observed on the MA2000w. Standard Printer MIB
tables are used where available; Kyocera enterprise OIDs are kept separately
because their meaning was established from the original NetViewer log and
cross-checked against PJL output.
"""

from __future__ import annotations

from .parser import PrinterSnapshot, Tray
from .snmp import SnmpClient, VarBind

SCALAR_OIDS = {
    "sys_descr": "1.3.6.1.2.1.1.1.0",
    "sys_uptime": "1.3.6.1.2.1.1.3.0",
    "sys_name": "1.3.6.1.2.1.1.5.0",
    "device_status": "1.3.6.1.2.1.25.3.2.1.5.1",
    "printer_status": "1.3.6.1.2.1.25.3.5.1.1.1",
    "model": "1.3.6.1.4.1.1347.43.5.1.1.1.1",
    "base_model": "1.3.6.1.4.1.1347.43.5.1.1.36.1",
    "serial": "1.3.6.1.4.1.1347.43.5.1.1.28.1",
    "firmware": "1.3.6.1.4.1.1347.43.5.4.1.5.1.1",
    "ip": "1.3.6.1.4.1.1347.40.10.1.1.4.1",
    "subnet": "1.3.6.1.4.1.1347.40.10.1.1.6.1",
    "gateway": "1.3.6.1.4.1.1347.40.10.1.1.7.1",
    "mac": "1.3.6.1.2.1.2.2.1.6.1",
    # prtMarkerLifeCount. The MA2000w exposes the row as instance 1.1, so the
    # full instance OID ends in .4.1.1; querying .4.1 returns NoSuchInstance.
    "page_count": "1.3.6.1.2.1.43.10.2.1.4.1.1",
    "scan_count": "1.3.6.1.4.1.1347.46.10.1.1.5.3",
    "device_uptime": "1.3.6.1.4.1.1347.43.5.1.1.4.1",
    "sleep_mode": "1.3.6.1.4.1.1347.43.5.1.1.33.1",
    "auto_error_clear": "1.3.6.1.4.1.1347.43.5.1.1.34.1",
    "auto_error_clear_timeout": "1.3.6.1.4.1.1347.43.5.1.1.35.1",
    "form_feed_timeout": "1.3.6.1.4.1.1347.43.5.1.1.22.1",
}

SUPPLIES = "1.3.6.1.2.1.43.11.1.1"
INPUTS = "1.3.6.1.2.1.43.8.2.1"
ALERTS = "1.3.6.1.2.1.43.18.1.1"
CONSOLE = "1.3.6.1.2.1.43.16.5.1"

# Only the columns that are mapped below are requested. Walking the whole
# subtree costs one GETNEXT per cell (hundreds of requests on the MA2000w);
# asking for these columns together costs one request per row.
SUPPLY_COLUMNS = (4, 5, 6, 7, 8, 9)
INPUT_COLUMNS = (9, 10, 11, 12, 15, 18)
ALERT_COLUMNS = (2, 3, 4, 5, 6, 7, 8, 9)

# Enumerations from IANA-PRINTER-MIB / RFC 3805 PrtAlertSeverityLevelTC,
# PrtAlertTrainingLevelTC and PrtAlertGroupTC.  The alert code table is kept
# deliberately small: only codes verified against the standard registry are
# named, while the raw integer always remains available.
ALERT_SEVERITY_NAMES = {
    1: "other",
    3: "critical",
    4: "warning",
    5: "warning_binary_change_event",
}

ALERT_TRAINING_LEVEL_NAMES = {
    1: "other",
    2: "unknown",
    3: "untrained",
    4: "trained",
    5: "field_service",
    6: "management",
    7: "no_intervention_required",
}

ALERT_GROUP_NAMES = {
    1: "other",
    2: "unknown",
    3: "host_resources_storage",
    4: "host_resources_device",
    5: "general_printer",
    6: "cover",
    7: "localization",
    8: "input",
    9: "output",
    10: "marker",
    11: "marker_supplies",
    12: "marker_colorant",
    13: "media_path",
    14: "channel",
    15: "interpreter",
    16: "console_display_buffer",
    17: "console_lights",
    18: "alert",
    30: "fin_device",
    31: "fin_supply",
    32: "fin_supply_media_input",
    33: "fin_attribute",
}

ALERT_CODE_NAMES = {
    # PrtAlertCodeTC markerFuserUnderTemperature.  MA2000w reports this
    # non-critical warning while the fuser is cold in sleep mode.
    1001: "marker_fuser_under_temperature",
}

CONSOLE_COLUMNS = (2,)

DEVICE_STATUS_NAMES = {
    1: "unknown",
    2: "running",
    3: "warning",
    4: "testing",
    5: "down",
}

PRINTER_STATUS_NAMES = {
    1: "other",
    2: "unknown",
    3: "idle",
    4: "printing",
    5: "warmup",
}

SUPPLY_UNIT_NAMES = {
    1: "other",
    2: "unknown",
    3: "ten-thousandths-of-inches",
    4: "ten-thousandths-of-centimeters",
    5: "impressions",
    6: "sheets",
    7: "percent",
    8: "hours",
    9: "thousandths-of-ounces",
    10: "tenths-of-grams",
    11: "hundredths-of-liters",
    12: "thousandths-of-cubic-centimeters",
    13: "feet",
    14: "meters",
    15: "items",
    16: "thousandths-of-ounces",
    17: "tenths-of-grams",
    18: "hundredths-of-liters",
    19: "thousandths-of-cubic-centimeters",
    20: "feet",
    21: "meters",
    22: "items",
}


def _text(varbind: VarBind | None) -> str | None:
    if varbind is None:
        return None
    value = varbind.value
    if value is None:
        return None
    if isinstance(value, bytes):
        if varbind.tag == 0x40 and len(value) == 4:
            return ".".join(str(byte) for byte in value)
        text = value.decode("utf-8", "replace")
    else:
        text = str(value)
    text = text.replace("\x00", "").strip()
    return text or None


def _integer(varbind: VarBind | None) -> int | None:
    if varbind is None or not isinstance(varbind.value, int):
        return None
    return varbind.value


def _mac(varbind: VarBind | None) -> str | None:
    if varbind is None:
        return None
    value = varbind.value
    if isinstance(value, bytes):
        if len(value) == 6:
            return ":".join(f"{byte:02X}" for byte in value)
        return value.hex().upper()
    return _text(varbind)


def _on_off(varbind: VarBind | None) -> str | None:
    value = _integer(varbind)
    if value == 1:
        return "ON"
    if value == 0:
        return "OFF"
    return None


def _table_rows(root: str, varbinds: list[VarBind]) -> list[tuple[str, dict[int, VarBind]]]:
    rows: dict[str, dict[int, VarBind]] = {}
    prefix = root + "."
    for varbind in varbinds:
        if not varbind.oid.startswith(prefix):
            continue
        column, separator, instance = varbind.oid[len(prefix) :].partition(".")
        if not separator:
            continue
        try:
            column_number = int(column)
        except ValueError:
            continue
        rows.setdefault(instance, {})[column_number] = varbind

    def sort_key(item: tuple[str, dict[int, VarBind]]) -> tuple:
        parts = item[0].split(".")
        return tuple(int(part) if part.isdigit() else 0 for part in parts)

    return sorted(rows.items(), key=sort_key)


def _format_uptime(varbind: VarBind | None) -> int | None:
    ticks = _integer(varbind)
    return None if ticks is None else ticks // 100


def collect_snmp_snapshot(
    host: str,
    *,
    community: str = "public",
    version: str = "1",
    port: int = 161,
    timeout: float = 1.5,
    retries: int = 2,
) -> PrinterSnapshot:
    """Read a printer snapshot through SNMP without modifying device state."""
    client = SnmpClient(
        host,
        community=community,
        version=version,
        port=port,
        timeout=timeout,
        retries=retries,
    )
    # The MA2000w's SNMP agent drops requests when several query streams are
    # sent at once (measured: 12.7 s in parallel vs 3.1 s sequentially), so the
    # tables are read one after another.
    values = {
        varbind.oid: varbind for varbind in client.get(list(SCALAR_OIDS.values()))
    }
    supplies = client.walk_rows(SUPPLIES, SUPPLY_COLUMNS, sentinel_column=8)
    inputs = client.walk_rows(INPUTS, INPUT_COLUMNS, sentinel_column=10)
    alerts = client.walk_rows(ALERTS, ALERT_COLUMNS, sentinel_column=3)
    console = client.walk_rows(CONSOLE, CONSOLE_COLUMNS, sentinel_column=2)

    snapshot = PrinterSnapshot()
    snapshot.model = _text(values.get(SCALAR_OIDS["model"]))
    snapshot.serial = _text(values.get(SCALAR_OIDS["serial"]))
    snapshot.firmware = _text(values.get(SCALAR_OIDS["firmware"]))

    device_status = _integer(values.get(SCALAR_OIDS["device_status"]))
    printer_status = _integer(values.get(SCALAR_OIDS["printer_status"]))
    auto_error_clear_raw = _integer(
        values.get(SCALAR_OIDS["auto_error_clear_timeout"])
    )
    form_feed_timeout_raw = _integer(values.get(SCALAR_OIDS["form_feed_timeout"]))
    auto_error_clear_timeout = (
        auto_error_clear_raw * 5 if auto_error_clear_raw is not None else None
    )
    form_feed_timeout = (
        form_feed_timeout_raw * 5 if form_feed_timeout_raw is not None else None
    )
    if device_status in (2, 3):
        snapshot.online = True
    elif device_status == 5:
        snapshot.online = False

    snapshot.network = {
        key: text
        for key, text in (
            ("interface", "NET"),
            ("ip", _text(values.get(SCALAR_OIDS["ip"]))),
            ("gateway", _text(values.get(SCALAR_OIDS["gateway"]))),
            ("subnet", _text(values.get(SCALAR_OIDS["subnet"]))),
            ("mac", _mac(values.get(SCALAR_OIDS["mac"]))),
        )
        if text
    }

    supply_rows = []
    for instance, columns in _table_rows(SUPPLIES, supplies):
        level = _integer(columns.get(9))
        capacity = _integer(columns.get(8))
        unit = _integer(columns.get(7))
        row = {
            "index": instance,
            "class": _integer(columns.get(4)),
            "type": _integer(columns.get(5)),
            "description": _text(columns.get(6)),
            "unit": unit,
            "unit_name": SUPPLY_UNIT_NAMES.get(unit),
            "max_capacity": capacity,
            "level": level,
        }
        if level is not None and capacity and capacity > 0:
            row["percent"] = round(level * 100 / capacity)
        supply_rows.append(row)
    snapshot.snmp["supplies"] = supply_rows

    for row in supply_rows:
        if row.get("type") == 3 and row.get("percent") is not None:
            snapshot.toner_level = int(row["percent"])
            break

    input_rows = []
    for instance, columns in _table_rows(INPUTS, inputs):
        name = _text(columns.get(18)) or _text(columns.get(15))
        current = _integer(columns.get(10))
        row = {
            "index": instance,
            "name": name,
            "media": _text(columns.get(12)),
            "status": _integer(columns.get(11)),
            "max_capacity": _integer(columns.get(9)),
            "current_level": current,
        }
        input_rows.append(row)
        snapshot.input_trays.append(
            Tray(
                name=name or f"input-{instance}",
                paper=None,
                media=row["media"],
                capacity=(
                    str(row["max_capacity"])
                    if row["max_capacity"] is not None
                    else None
                ),
                remain=(
                    str(current)
                    if current is not None and current >= 0
                    else "UNKNOWN"
                ),
            )
        )
    snapshot.snmp["inputs"] = input_rows

    alert_rows = []
    for instance, columns in _table_rows(ALERTS, alerts):
        severity = _integer(columns.get(2))
        training_level = _integer(columns.get(3))
        group = _integer(columns.get(4))
        code = _integer(columns.get(7))
        alert_rows.append(
            {
                "index": instance,
                "severity": severity,
                "severity_name": ALERT_SEVERITY_NAMES.get(severity),
                "training_level": training_level,
                "training_level_name": ALERT_TRAINING_LEVEL_NAMES.get(
                    training_level
                ),
                "group": group,
                "group_name": ALERT_GROUP_NAMES.get(group),
                "group_index": _integer(columns.get(5)),
                "location": _integer(columns.get(6)),
                "code": code,
                "code_name": ALERT_CODE_NAMES.get(code),
                "description": _text(columns.get(8)),
                "time_ticks": _integer(columns.get(9)),
            }
        )
    snapshot.snmp["alerts"] = alert_rows

    console_lines = []
    for instance, columns in _table_rows(CONSOLE, console):
        line = _text(columns.get(2))
        if line:
            console_lines.append({"index": instance, "text": line})
    snapshot.snmp["console_lines"] = console_lines
    if console_lines and not snapshot.display:
        snapshot.display = console_lines[0]["text"]

    snapshot.snmp.update(
        {
            "version": version,
            "community": community,
            "sys_descr": _text(values.get(SCALAR_OIDS["sys_descr"])),
            "sys_name": _text(values.get(SCALAR_OIDS["sys_name"])),
            "sys_uptime_seconds": _format_uptime(values.get(SCALAR_OIDS["sys_uptime"])),
            "base_model": _text(values.get(SCALAR_OIDS["base_model"])),
            "device_status": device_status,
            "device_status_name": DEVICE_STATUS_NAMES.get(device_status),
            "printer_status": printer_status,
            "printer_status_name": PRINTER_STATUS_NAMES.get(printer_status),
            "page_count": _integer(values.get(SCALAR_OIDS["page_count"])),
            "scan_count": _integer(values.get(SCALAR_OIDS["scan_count"])),
            "device_uptime_seconds": _integer(
                values.get(SCALAR_OIDS["device_uptime"])
            ),
            "sleep_mode": _on_off(values.get(SCALAR_OIDS["sleep_mode"])),
            "auto_error_clear": _on_off(
                values.get(SCALAR_OIDS["auto_error_clear"])
            ),
            "auto_error_clear_timeout_seconds": auto_error_clear_timeout,
            "form_feed_timeout_seconds": form_feed_timeout,
        }
    )
    if form_feed_timeout is not None:
        snapshot.timeout = form_feed_timeout
    return snapshot
