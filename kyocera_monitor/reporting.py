"""Stable, spreadsheet-friendly exports for device counters."""

from __future__ import annotations

import csv
import io


def _known_value(snapshot: dict, name: str) -> object | None:
    known = snapshot.get("kgetobj_known") or {}
    entry = known.get(name) if isinstance(known, dict) else None
    return entry.get("value") if isinstance(entry, dict) else None


def _csv_text(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value)
    # Keep device-supplied strings from becoming spreadsheet formulas.
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def counters_csv(devices: list[dict]) -> bytes:
    """Export one row per configured device, including explicit read errors."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "device",
            "model",
            "serial",
            "firmware",
            "status",
            "toner_percent",
            "page_count",
            "scan_count",
            "drum_counter",
            "drum_counter_max",
            "collected_at",
            "error",
        ]
    )
    for device in devices:
        snapshot = device.get("snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {}
        snmp = snapshot.get("snmp") or {}
        if not isinstance(snmp, dict):
            snmp = {}
        normal = snapshot.get("normal")
        status = "normal" if normal is True else "warning" if normal is False else "unknown"
        writer.writerow(
            [
                _csv_text(device.get("device")),
                _csv_text(snapshot.get("model")),
                _csv_text(snapshot.get("serial")),
                _csv_text(snapshot.get("firmware")),
                status,
                _csv_text(snapshot.get("toner_level")),
                _csv_text(snmp.get("page_count", _known_value(snapshot, "lifetime_counter"))),
                _csv_text(snmp.get("scan_count", _known_value(snapshot, "scan_count"))),
                _csv_text(_known_value(snapshot, "drum_counter")),
                _csv_text(_known_value(snapshot, "drum_counter_max")),
                _csv_text(device.get("collected_at")),
                _csv_text(device.get("error")),
            ]
        )
    return output.getvalue().encode("utf-8-sig")
