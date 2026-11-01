"""Read-only inspection of Kyocera network Push Scan settings.

The official Client Tool receives Push Scan settings through its status
pipeline, compares the configured destination with local interfaces, and then
launches a preset-specific scanner application.  Device status codes 89000
through 89999 encode the requested preset as ``code - 89000``.  This module
implements the read-only settings probe and event detector, but does not launch
or acknowledge a scan.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from datetime import datetime, timezone
from typing import Callable, Iterable, Iterator

from .snmp import SnmpClient, VarBind

PUSH_SCAN_ROOT = "1.3.6.1.4.1.1347.1001.4.1"
VENDOR_ALERT_STATUS_ROOT = "1.3.6.1.4.1.1347.43.18.2.1.3"
PUSH_SCAN_OIDS = {
    "interface": f"{PUSH_SCAN_ROOT}.1.0",
    "ipv4_address": f"{PUSH_SCAN_ROOT}.2.0",
    "result": f"{PUSH_SCAN_ROOT}.3.0",
    "ipv6_address": f"{PUSH_SCAN_ROOT}.4.0",
    "host_name": f"{PUSH_SCAN_ROOT}.5.0",
    "address_type": f"{PUSH_SCAN_ROOT}.6.0",
}

INTERFACE_NAMES = {
    0: "USB",
    1: "NETWORK",
}
ADDRESS_TYPE_NAMES = {
    1: "IPv4",
    2: "IPv6",
    3: "HOST_NAME",
}
RESULT_NAMES = {
    0: "OK",
    1: "NG",
}

EXECUTION_LIMITATION = (
    "Mapped local preset execution requires --push-scan-run and a unique "
    "0-30 slot binding; automatic result writeback is not implemented."
)
EVENT_LIMITATION = (
    "This listener-only event does not launch a scan; add --push-scan-run "
    "to execute the mapped local preset. Automatic result writeback is disabled."
)
PUSH_SCAN_STATUS_MIN = 89000
PUSH_SCAN_STATUS_MAX = 89999
PUSH_SCAN_PRESET_MAX = 30

_LEADING_C_NUMBER_RE = re.compile(
    r"^\s*([+-]?(?:0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*))"
)


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return None


def _ipv4(value: object) -> str | None:
    if isinstance(value, bytes) and len(value) == 4:
        return str(ipaddress.IPv4Address(value))
    if isinstance(value, str):
        try:
            return str(ipaddress.IPv4Address(value.strip()))
        except ipaddress.AddressValueError:
            return None
    return None


def _ipv6(value: object) -> str | None:
    if isinstance(value, bytes) and len(value) == 16:
        return str(ipaddress.IPv6Address(value))
    if isinstance(value, str):
        try:
            return str(ipaddress.IPv6Address(value.strip()))
        except ipaddress.AddressValueError:
            return None
    return None


def _text(value: object) -> str | None:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        return value
    return None


def _value(varbind: VarBind | None, decoder):
    if varbind is None:
        return None
    return decoder(varbind.value)


def local_host_identity(printer_host: str | None = None) -> dict[str, object]:
    """Return local addresses and names used by the official target checks."""

    addresses: set[str] = set()
    names: set[str] = set()
    try:
        host_name = socket.gethostname()
        names.add(host_name.casefold())
        names.add(socket.getfqdn(host_name).casefold())
    except OSError:
        pass
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None):
            addresses.add(str(ipaddress.ip_address(result[4][0])))
    except (OSError, ValueError):
        pass
    if printer_host:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                # connect() on UDP selects a route without sending a packet.
                probe.connect((printer_host, 9))
                addresses.add(str(ipaddress.ip_address(probe.getsockname()[0])))
        except (OSError, ValueError):
            pass
    return {
        "addresses": sorted(addresses),
        "host_names": sorted(name for name in names if name),
    }


def _target_value(
    address_type: int | None,
    objects: dict[str, object],
) -> str | None:
    if address_type == 1:
        return objects["ipv4_address"]["value"]
    if address_type == 2:
        return objects["ipv6_address"]["value"]
    if address_type == 3:
        return objects["host_name"]["value"]
    return None


def _is_unset_target(target: str | None, address_type: int | None) -> bool:
    if target is None or target == "":
        return True
    try:
        address = ipaddress.ip_address(target)
    except ValueError:
        return False
    if address_type == 1 and address == ipaddress.IPv4Address("0.0.0.0"):
        return True
    if address_type == 2 and address == ipaddress.IPv6Address("::"):
        return True
    return False


def _matches_local(
    target: str | None,
    address_type: int | None,
    local_identity: dict[str, object],
) -> bool | None:
    if _is_unset_target(target, address_type):
        return False
    if target is None:
        return None
    if address_type == 3:
        local_names = {
            str(name).casefold()
            for name in local_identity.get("host_names", [])
        }
        return target.casefold() in local_names
    try:
        normalized = str(ipaddress.ip_address(target))
    except ValueError:
        return None
    local_addresses = {
        str(ipaddress.ip_address(str(address)))
        for address in local_identity.get("addresses", [])
    }
    return normalized in local_addresses


def interpret_push_scan(
    varbinds: Iterable[VarBind],
    *,
    host: str,
    local_identity: dict[str, object] | None = None,
) -> dict[str, object]:
    """Decode Push Scan objects without modifying device state."""

    by_oid = {varbind.oid: varbind for varbind in varbinds}
    raw = {
        name: by_oid.get(oid)
        for name, oid in PUSH_SCAN_OIDS.items()
    }
    interface = _value(raw["interface"], _integer)
    address_type = _value(raw["address_type"], _integer)
    result = _value(raw["result"], _integer)
    values = {
        "interface": interface,
        "ipv4_address": _value(raw["ipv4_address"], _ipv4),
        "result": result,
        "ipv6_address": _value(raw["ipv6_address"], _ipv6),
        "host_name": _value(raw["host_name"], _text),
        "address_type": address_type,
    }
    objects = {
        name: {
            "oid": PUSH_SCAN_OIDS[name],
            "available": raw[name] is not None,
            "type": raw[name].type_name if raw[name] is not None else None,
            "raw": (
                raw[name].value.hex()
                if raw[name] is not None and isinstance(raw[name].value, bytes)
                else raw[name].value if raw[name] is not None else None
            ),
            "value": values[name],
            "display": (
                INTERFACE_NAMES.get(interface, f"UNKNOWN({interface})")
                if name == "interface" and interface is not None
                else ADDRESS_TYPE_NAMES.get(
                    address_type, f"UNKNOWN({address_type})"
                )
                if name == "address_type" and address_type is not None
                else RESULT_NAMES.get(result, f"UNKNOWN({result})")
                if name == "result" and result is not None
                else values[name]
            ),
        }
        for name in PUSH_SCAN_OIDS
    }

    identity = local_identity or local_host_identity(host)
    target = _target_value(address_type, objects)
    target_matches_local = _matches_local(target, address_type, identity)
    if interface is None:
        state = "unavailable"
        ready: bool | None = None
        summary = "Required Push Scan interface state is unavailable."
    elif interface == 0:
        state = "usb_destination"
        ready = False
        summary = "The device currently selects a USB Push Scan destination."
    elif address_type not in ADDRESS_TYPE_NAMES:
        state = "unavailable"
        ready = None
        summary = "The Push Scan address type is unavailable or unrecognized."
    elif _is_unset_target(target, address_type):
        state = "not_configured"
        ready = False
        summary = "Network Push Scan is selected but no target is configured."
    elif target_matches_local is True:
        state = "ready"
        ready = True
        summary = "The configured Push Scan target matches this computer."
    elif target_matches_local is False:
        state = "other_host"
        ready = False
        summary = "The configured Push Scan target does not match this computer."
    else:
        state = "unavailable"
        ready = None
        summary = "The configured Push Scan target could not be validated."

    return {
        "host": host,
        "read_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
        "objects": objects,
        "interface": {
            "raw": interface,
            "name": INTERFACE_NAMES.get(interface, "UNKNOWN"),
        },
        "address_type": {
            "raw": address_type,
            "name": ADDRESS_TYPE_NAMES.get(address_type, "UNKNOWN"),
        },
        "target": target,
        "target_matches_local": target_matches_local,
        "last_result": {
            "raw": result,
            "name": RESULT_NAMES.get(result, "UNKNOWN"),
            "scope": "last_reported_result",
        },
        "local_identity": identity,
        "readiness": {
            "ready": ready,
            "state": state,
            "summary": summary,
        },
        "execution": {
            "supported": True,
            "state": "mapped_cli_listener",
            "trigger_observed": False,
            "listener_entrypoint": "kyocera-monitor --push-scan-listen",
            "execution_option": "--push-scan-run",
            "preset_selection": "status_code_minus_89000",
            "result_writeback_supported": False,
            "reason": EXECUTION_LIMITATION,
        },
        "limitations": [
            EXECUTION_LIMITATION,
            (
                "The result object is the last result reported by the device, "
                "not a timestamped event generated by this probe."
            ),
        ],
    }


def read_push_scan(
    host: str,
    *,
    community: str = "public",
    version: str = "2c",
    port: int = 161,
    timeout: float = 1.5,
    retries: int = 2,
    local_identity: dict[str, object] | None = None,
) -> dict[str, object]:
    """Read and decode Push Scan state through SNMP."""

    client = SnmpClient(
        host,
        community=community,
        version=version,
        port=port,
        timeout=timeout,
        retries=retries,
    )
    varbinds = client.get(PUSH_SCAN_OIDS.values())
    return interpret_push_scan(
        varbinds,
        host=host,
        local_identity=local_identity,
    )


def parse_vendor_status_code(value: object) -> int | None:
    """Parse the leading number as Client Tool's ``strtoul(value, NULL, 0)``.

    The vendor alert-display column is an OctetString even though its useful
    value is numeric.  The official network monitor parses the leading number
    with base auto-detection and ignores the rest of the row.
    """

    if isinstance(value, bytes):
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError:
            return None
    elif isinstance(value, str):
        text = value
    elif isinstance(value, int) and not isinstance(value, bool):
        return value
    else:
        return None
    match = _LEADING_C_NUMBER_RE.match(text)
    if match is None:
        return None
    token = match.group(1)
    sign = -1 if token.startswith("-") else 1
    unsigned = token.lstrip("+-")
    if unsigned.lower().startswith("0x"):
        number = int(unsigned[2:], 16)
    elif len(unsigned) > 1 and unsigned.startswith("0"):
        number = int(unsigned[1:], 8)
    else:
        number = int(unsigned, 10)
    return sign * number


def vendor_status_codes(varbinds: Iterable[VarBind]) -> list[int]:
    """Return parseable status codes in the official table-row order."""

    codes: list[int] = []
    for varbind in varbinds:
        if not varbind.oid.startswith(VENDOR_ALERT_STATUS_ROOT + "."):
            continue
        code = parse_vendor_status_code(varbind.value)
        if code is not None:
            codes.append(code)
    return codes


def read_vendor_status_codes(
    host: str,
    *,
    community: str = "public",
    version: str = "2c",
    port: int = 161,
    timeout: float = 1.5,
    retries: int = 2,
    max_rows: int = 64,
) -> list[int]:
    """Read the vendor alert-status column through read-only SNMP GETNEXT."""

    client = SnmpClient(
        host,
        community=community,
        version=version,
        port=port,
        timeout=timeout,
        retries=retries,
    )
    return vendor_status_codes(
        client.walk(VENDOR_ALERT_STATUS_ROOT, max_rows=max_rows)
    )


def push_scan_event(code: int, *, host: str) -> dict[str, object] | None:
    """Convert an official 89xxx status code into a Push Scan event."""

    if not PUSH_SCAN_STATUS_MIN <= code <= PUSH_SCAN_STATUS_MAX:
        return None
    preset = code - PUSH_SCAN_STATUS_MIN
    return {
        "event": "push_scan_request",
        "host": host,
        "status_code": code,
        "preset_number": preset,
        "official_preset_range": {
            "min": 0,
            "max": PUSH_SCAN_PRESET_MAX,
            "within_range": preset <= PUSH_SCAN_PRESET_MAX,
        },
        "observed_at": datetime.now(tz=timezone.utc).isoformat(
            timespec="seconds"
        ),
        "execution_state": "listener_only",
        "execution_supported": False,
        "result_writeback_supported": False,
        "limitation": EVENT_LIMITATION,
    }


def iter_push_scan_events(
    host: str,
    read_codes: Callable[[], list[int]],
    *,
    poll_interval: float = 2.0,
    max_polls: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[tuple[int, list[int], dict[str, object] | None]]:
    """Poll the official vendor status column and yield trigger transitions.

    Each tuple contains ``(poll_number, codes, event)``.  ``event`` is only
    set when the first (official) code changes into the Push Scan range, which
    prevents a persistent 89xxx status from launching the same preset
    repeatedly.
    """

    if poll_interval < 0:
        raise ValueError("poll_interval must be non-negative")
    if max_polls is not None and max_polls < 1:
        raise ValueError("max_polls must be positive or None")
    previous: int | None = None
    poll = 0
    while max_polls is None or poll < max_polls:
        poll += 1
        codes = read_codes()
        current = codes[0] if codes else None
        event = None
        if current != previous and current is not None:
            event = push_scan_event(current, host=host)
        previous = current
        yield poll, codes, event
        if max_polls is not None and poll >= max_polls:
            break
        sleep(poll_interval)


def format_push_scan(result: dict[str, object]) -> str:
    """Render a compact human-readable Push Scan inspection."""

    objects = result["objects"]
    readiness = result["readiness"]
    execution = result["execution"]
    target = result["target"] or "-"
    matches = result["target_matches_local"]
    match_text = (
        "yes" if matches is True else "no" if matches is False else "unknown"
    )
    return "\n".join(
        [
            f"Push Scan interface: {objects['interface']['display'] or 'unknown'}",
            (
                "Push Scan address type: "
                f"{objects['address_type']['display'] or 'unknown'}"
            ),
            f"Push Scan target: {target}",
            f"Target matches this computer: {match_text}",
            (
                "Last reported result: "
                f"{objects['result']['display'] or 'unknown'}"
            ),
            f"Readiness: {readiness['state']}",
            f"Execution: {execution['state']}",
        ]
    )


__all__ = [
    "ADDRESS_TYPE_NAMES",
    "INTERFACE_NAMES",
    "PUSH_SCAN_OIDS",
    "PUSH_SCAN_PRESET_MAX",
    "PUSH_SCAN_ROOT",
    "PUSH_SCAN_STATUS_MAX",
    "PUSH_SCAN_STATUS_MIN",
    "RESULT_NAMES",
    "VENDOR_ALERT_STATUS_ROOT",
    "format_push_scan",
    "interpret_push_scan",
    "iter_push_scan_events",
    "local_host_identity",
    "parse_vendor_status_code",
    "push_scan_event",
    "read_push_scan",
    "read_vendor_status_codes",
    "vendor_status_codes",
]
