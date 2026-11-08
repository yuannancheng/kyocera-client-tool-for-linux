"""Command-line entry point for the Linux Kyocera status monitor."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import threading
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path

from .config import collect_config, collect_config_snmp, set_config_integer
from .config_snapshot import (
    ConfigSnapshotError,
    build_config_snapshot,
    compare_config_snapshots,
    load_config_snapshot,
    save_config_snapshot,
)
from .config_write_candidates import (
    ConfigCandidateError,
    build_config_candidate_report,
)
from .config_write_audit import (
    ConfigWriteAuditError,
    build_safe_audit_plan,
    execute_safe_audit,
)
from .config_write_plan import (
    ConfigWritePlanError,
    build_config_write_plan,
)
from .config_write_executor import (
    ConfigWriteExecutionError,
    execute_authorized_config_experiment,
)
from .config_web import ConfigWorkbench
from .discovery import discover
from .parser import PrinterSnapshot, parse_response
from .kmscn_raw import RawScanError, decode_raw
from .pjl import (
    QUERY_SEQUENCE,
    USB_QUERY_SEQUENCE,
    PjlError,
    open_channel,
    query_merged,
)
from .push_scan import (
    format_push_scan,
    iter_push_scan_events,
    read_push_scan,
    read_vendor_status_codes,
)
from .push_scan_exec import execute_push_scan_event
from .preferences import SettingsError, SettingsStore
from .snmp_status import collect_snmp_snapshot
from .snmp import BerError, SnmpClient
from .scan import (
    LOCAL_OUTPUT_FORMATS,
    ScanJobManager,
    ScanError,
    ScanOptions,
    ScanResult,
    export_pages,
    scan_device,
    write_outputs,
)
from .usb import (
    UsbError,
    discover_usb_printers,
    merge_usb_printers,
    select_usb_printer,
)
from .usb_libusb import discover_libusb_printers
from .usb_scan import (
    UsbScanError,
    UsbScanParameters,
    UsbScannerControl,
    probe_scanner,
)
from .updates import (
    DEFAULT_UPDATE_URL,
    UpdateCheckError,
    UpdateChecker,
)
from .wifi import (
    SECURITY_MODES,
    WifiError,
    WifiWorkbench,
    connect_access_point,
    read_wifi_status,
    scan_access_points,
)
from .web import DeviceRegistry, run_server


def format_snapshot(snapshot: PrinterSnapshot) -> str:
    status = "unknown"
    if snapshot.status_code is not None:
        status = str(snapshot.status_code)
        if snapshot.normal is True:
            status += " (normal)"
        elif snapshot.normal is False:
            status += " (warning)"
    elif snapshot.snmp:
        printer_status = snapshot.snmp.get("printer_status_name") or "unknown"
        device_status = snapshot.snmp.get("device_status_name") or "unknown"
        status = f"{printer_status} (device: {device_status})"
    lines = [
        f"Model: {snapshot.model or 'unknown'}",
        f"Serial: {snapshot.serial or 'unknown'}",
        f"Firmware: {snapshot.firmware or 'unknown'}",
        f"Status: {status}",
        f"Display: {snapshot.display or 'unknown'}",
        f"Online: {snapshot.online}",
        "Toner: " + (
            f"{snapshot.toner_level}%"
            if snapshot.toner_level is not None
            else "unknown"
        ),
        "Coverage: " + (
            f"{snapshot.coverage}%"
            if snapshot.coverage is not None
            else "unknown"
        ),
    ]
    if snapshot.network:
        lines.append(
            "Network: {ip} gw={gateway} mask={subnet} mac={mac}".format(
                **snapshot.network
            )
        )
    for tray in snapshot.tray_status:
        display = tray.to_dict()
        details = " ".join(
            str(value)
            for value in (
                display.get("display_status"),
                display.get("display_paper"),
            )
            if value and value != "—"
        )
        lines.append(
            f"{display['display_name']}: {details}; "
            f"remaining={display['display_remain']}".rstrip()
        )
    for item in snapshot.kgetobj_known.values():
        unit = f" {item['unit']}" if item.get("unit") else ""
        inferred = " (inferred)" if item.get("confidence") == "inferred" else ""
        lines.append(f"{item['label']}: {item['value']}{unit}{inferred}")
    if snapshot.snmp:
        if snapshot.snmp.get("scan_count") is not None:
            lines.append(f"Scan count: {snapshot.snmp['scan_count']}")
        if snapshot.snmp.get("page_count") is not None:
            lines.append(f"Page count: {snapshot.snmp['page_count']}")
        if snapshot.snmp.get("sleep_mode"):
            lines.append(f"Sleep mode: {snapshot.snmp['sleep_mode']}")
        if snapshot.snmp.get("auto_error_clear"):
            timeout = snapshot.snmp.get("auto_error_clear_timeout_seconds")
            suffix = f" ({timeout} s)" if timeout is not None else ""
            lines.append(
                f"Auto error clear: {snapshot.snmp['auto_error_clear']}{suffix}"
            )
        if snapshot.snmp.get("form_feed_timeout_seconds") is not None:
            lines.append(
                "Form feed timeout: "
                f"{snapshot.snmp['form_feed_timeout_seconds']} s"
            )
        for alert in snapshot.snmp.get("alerts") or []:
            description = alert.get("description") or alert.get("code_name") or ""
            code_name = alert.get("code_name")
            if (
                code_name
                and alert.get("description")
                and code_name not in description
            ):
                description = f"{code_name} ({description})"
            lines.append(
                (
                    "Alert: severity={severity} group={group} "
                    "code={code} {description}"
                ).format(
                    severity=alert.get("severity_name") or alert.get("severity"),
                    group=alert.get("group_name") or alert.get("group"),
                    code=alert.get("code"),
                    description=description,
                ).rstrip()
            )
    return "\n".join(lines)


def usb_scan_parameters_from_cli(args) -> UsbScanParameters:
    """Map the user-facing scan tokens onto recovered USB integer fields."""

    color = {
        None: 3,
        "FULL_COLOR": 3,
        "GRAYSCALE": 2,
        "BLACK_AND_WHITE": 1,
    }
    if args.scan_color not in color:
        raise UsbScanError(
            "the recovered USB request does not yet model "
            f"scan color {args.scan_color}"
        )
    resolution = {
        None: 300,
        "RESOLUTION_200X200": 200,
        "RESOLUTION_300X300": 300,
        "RESOLUTION_400X400": 400,
        "RESOLUTION_600X600": 600,
    }
    if args.scan_resolution not in resolution:
        raise UsbScanError(
            "the recovered USB request does not yet model "
            f"resolution {args.scan_resolution}"
        )
    original_image = {
        None: 3,
        "TEXT": 1,
        "PHOTO": 2,
        "TEXT_AND_PHOTO": 3,
        "FOR_OCR": 4,
    }
    if args.scan_original_image not in original_image:
        raise UsbScanError(
            "the recovered USB request does not yet model "
            f"original image {args.scan_original_image}"
        )
    placement = {
        None: 1,
        "AUTO": 1,
        "ADF": 2,
        "PLATEN": 3,
    }
    if args.scan_original_placement not in placement:
        raise UsbScanError(
            f"unsupported USB original placement: "
            f"{args.scan_original_placement}"
        )
    duplex = {
        None: 0,
        "SIMPLEX": 0,
        "DUPLEX": 1,
    }
    if args.scan_duplex not in duplex:
        raise UsbScanError(
            f"unsupported USB duplex mode: {args.scan_duplex}"
        )
    if args.scan_continuous not in {"OFF", None}:
        raise UsbScanError("continuous USB scan is not yet modeled")
    if args.scan_max_pages != 1:
        raise UsbScanError("USB capture currently supports one page")
    if args.scan_device_format != "RAW":
        raise UsbScanError("USB scan transport only requests RAW image data")
    return UsbScanParameters(
        original_size=4,
        feed_method=placement[args.scan_original_placement],
        resolution=resolution[args.scan_resolution],
        color_mode=color[args.scan_color],
        original_image=original_image[args.scan_original_image],
        duplex=duplex[args.scan_duplex],
        duplex_edge=0,
    )


def collect(
    host: str | None,
    device: str | None,
    port: int,
    timeout: float,
    idle: float,
    commands=QUERY_SEQUENCE,
):
    result = None
    for attempt in range(2):
        with open_channel(host=host, device=device, port=port) as channel:
            raw = query_merged(channel, commands, timeout=timeout, idle=idle)
        snapshot = parse_response(raw)
        result = raw, snapshot
        if snapshot.model is not None and snapshot.status_code is not None:
            break
        if attempt == 0:
            time.sleep(0.2)
    return result


def collect_snmp(args) -> tuple[bytes, PrinterSnapshot]:
    if not args.host:
        raise PjlError("--snmp requires --host")
    snapshot = collect_snmp_snapshot(
        args.host,
        community=args.snmp_community,
        version=args.snmp_version,
        port=args.snmp_port,
        timeout=args.snmp_timeout,
        retries=args.snmp_retries,
    )
    return b"", snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read Kyocera printer status and run explicitly authorized "
            "configuration experiments"
        )
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--host", help="printer IPv4 address or hostname")
    target.add_argument("--device", help="USB character device, e.g. /dev/usb/lp0")
    target.add_argument(
        "--usb",
        action="store_true",
        help="auto-detect a USB printer (usblp or libusb fallback)",
    )
    parser.add_argument(
        "--list-usb",
        action="store_true",
        help="list detected USB printers and exit",
    )
    parser.add_argument(
        "--usb-scan-info",
        action="store_true",
        help=(
            "probe the vendor USB scanner connect/machine-info/version "
            "protocol without capturing an image"
        ),
    )
    parser.add_argument(
        "--usb-scan-capture",
        type=Path,
        metavar="PATH",
        help=(
            "attempt the statically recovered vendor USB RAW scan and export "
            "one page; experimental until the response stream is hardware-verified"
        ),
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="discover printers through SNMP broadcast and WS-Discovery",
    )
    parser.add_argument(
        "--discover-timeout",
        type=float,
        default=2.5,
        help="discovery collection window in seconds (default: 2.5)",
    )
    parser.add_argument(
        "--discover-subnet",
        help="also probe every host in this IPv4 CIDR (maximum /22)",
    )
    parser.add_argument(
        "--discover-no-wsd",
        action="store_true",
        help="skip the WS-Discovery probe",
    )
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--idle", type=float, default=1.5)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--raw", action="store_true", help="emit raw PJL response")
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="check the published update metadata and exit",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="run an integrated KM-WSDL network scan",
    )
    parser.add_argument(
        "--scan-output",
        type=Path,
        help="scan output file or destination directory",
    )
    parser.add_argument(
        "--scan-format",
        choices=LOCAL_OUTPUT_FORMATS,
        default="png",
        help="local scan format (default: png)",
    )
    parser.add_argument(
        "--scan-color",
        choices=(
            "FULL_COLOR",
            "GRAYSCALE",
            "BLACK_AND_WHITE",
            "AUTO_BLACK_AND_WHITE",
            "AUTO_GRAYSCALE",
        ),
        help="official KM-WSDL color selection override",
    )
    parser.add_argument(
        "--scan-resolution",
        choices=(
            "RESOLUTION_150X150",
            "RESOLUTION_200X100",
            "RESOLUTION_200X200",
            "RESOLUTION_200X400",
            "RESOLUTION_300X300",
            "RESOLUTION_400X400",
            "RESOLUTION_600X600",
        ),
        help="official KM-WSDL resolution override",
    )
    parser.add_argument(
        "--scan-original-image",
        choices=(
            "TEXT",
            "TEXT_AND_PHOTO",
            "PHOTO",
            "FOR_OCR",
            "MAP",
            "LIGHT_TEXT",
        ),
        help="official KM-WSDL original image override",
    )
    parser.add_argument(
        "--scan-max-pages",
        type=int,
        default=1,
        help="maximum pages to retain and export (default: 1)",
    )
    parser.add_argument("--scan-max-polls", type=int, default=60)
    parser.add_argument("--scan-poll-interval", type=float, default=1.0)
    parser.add_argument("--scan-timeout", type=float, default=30.0)
    parser.add_argument(
        "--scan-max-response-bytes",
        type=int,
        default=64 * 1024 * 1024,
    )
    parser.add_argument(
        "--scan-device-format",
        choices=(
            "PDF",
            "TIFF",
            "JPEG",
            "HIGH_COMPRESSION_PDF",
            "XPS",
            "RAW",
        ),
        default="RAW",
    )
    parser.add_argument(
        "--scan-duplex",
        choices=("SIMPLEX", "DUPLEX", "BOOKLET"),
    )
    parser.add_argument(
        "--scan-original-placement",
        choices=("AUTO", "PLATEN", "ADF"),
    )
    parser.add_argument(
        "--scan-continuous",
        choices=("OFF", "ON"),
    )
    parser.add_argument("--scan-operation-id")
    parser.add_argument("--scan-retrieve-only", action="store_true")
    parser.add_argument("--scan-https", action="store_true")
    parser.add_argument("--scan-port", type=int)
    parser.add_argument("--scan-insecure", action="store_true")
    parser.add_argument("--watch", type=float, metavar="SECONDS", help="poll repeatedly")
    parser.add_argument("--count", type=int, default=0, help="stop after N polls")
    parser.add_argument("--expect-model", help="fail when the printer model differs")
    parser.add_argument(
        "--web",
        action="store_true",
        help="serve a read-only local dashboard instead of printing",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="open the dashboard in a native GTK window",
    )
    parser.add_argument(
        "--web-open",
        action="store_true",
        help="open the dashboard in the default browser with --web",
    )
    parser.add_argument(
        "--web-bind",
        default="127.0.0.1",
        help="dashboard bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--web-port", type=int, default=8080, help="dashboard port (default: 8080)"
    )
    parser.add_argument(
        "--snmp",
        action="store_true",
        help="read status through SNMP instead of PJL (read-only)",
    )
    parser.add_argument(
        "--push-scan",
        action="store_true",
        help=(
            "inspect network Push Scan destination and readiness "
            "without receiving or executing a scan"
        ),
    )
    wifi_mode = parser.add_mutually_exclusive_group()
    wifi_mode.add_argument(
        "--wifi-status",
        action="store_true",
        help="read the current Wi-Fi connection state over PJL",
    )
    wifi_mode.add_argument(
        "--wifi-scan",
        action="store_true",
        help="trigger the official access-point scan and list results",
    )
    wifi_mode.add_argument(
        "--wifi-connect",
        metavar="SSID",
        help="connect to an access point using the official SET sequence",
    )
    parser.add_argument(
        "--wifi-security",
        type=int,
        choices=tuple(SECURITY_MODES),
        help="security-mode integer required with --wifi-connect",
    )
    parser.add_argument(
        "--wifi-bssid",
        default="",
        help="optional BSSID used with --wifi-connect",
    )
    parser.add_argument(
        "--wifi-wep-index",
        type=int,
        default=0,
        help="WEP key index for security mode 1 (default: 0)",
    )
    parser.add_argument(
        "--wifi-password-env",
        default="KYOCERA_WIFI_PASSWORD",
        help=(
            "environment variable containing the WEP/PSK secret; "
            "prompts securely when unset"
        ),
    )
    parser.add_argument(
        "--wifi-scan-timeout",
        type=float,
        default=20.0,
        help="seconds to wait for an access-point scan (default: 20)",
    )
    parser.add_argument(
        "--wifi-connect-timeout",
        type=float,
        default=25.0,
        help="seconds to wait for Wi-Fi association (default: 25)",
    )
    parser.add_argument(
        "--push-scan-listen",
        action="store_true",
        help=(
            "listen for official 89xxx Push Scan status events through "
            "read-only SNMP polling"
        ),
    )
    parser.add_argument(
        "--push-scan-run",
        action="store_true",
        help=(
            "with --push-scan-listen, execute the local preset mapped to "
            "the observed 0-30 Push Scan slot"
        ),
    )
    parser.add_argument(
        "--push-scan-poll-interval",
        type=float,
        default=2.0,
        help="seconds between Push Scan status polls (default: 2)",
    )
    parser.add_argument(
        "--push-scan-max-polls",
        type=int,
        default=0,
        help="stop after N status polls; 0 runs until interrupted",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help=(
            "dump the 147 Client Tool configuration objects through "
            "read-only PJL KGETOBJ"
        ),
    )
    parser.add_argument(
        "--config-snmp-version",
        choices=("1", "2c"),
        default="2c",
        help="SNMP version for --config --snmp (default: 2c)",
    )
    parser.add_argument(
        "--config-save",
        metavar="PATH",
        help="save the complete --config read as a private snapshot",
    )
    parser.add_argument(
        "--config-compare",
        metavar="PATH",
        help="compare the current --config read with a saved snapshot",
    )
    parser.add_argument(
        "--config-candidates",
        action="store_true",
        help="review the next configuration write candidate without writing",
    )
    parser.add_argument(
        "--config-audit-safe",
        metavar="PATH",
        help=(
            "exercise a bounded whitelist of harmless integer fields and "
            "restore each value"
        ),
    )
    parser.add_argument(
        "--config-plan",
        metavar="PATH",
        help="build a dry-run write plan from a saved configuration snapshot",
    )
    parser.add_argument(
        "--config-set",
        metavar="ITEM_ID=VALUE",
        help="requested value for --config-plan or --config-apply",
    )
    parser.add_argument(
        "--config-apply",
        metavar="PATH",
        help="execute an explicitly authorized single-field experiment",
    )
    parser.add_argument(
        "--config-confirm",
        metavar="TOKEN",
        help="confirmation token emitted by --config-plan for --config-apply",
    )
    parser.add_argument(
        "--config-force",
        action="store_true",
        help="allow --config-save to replace an existing file",
    )
    parser.add_argument(
        "--config-allow-target-mismatch",
        action="store_true",
        help="allow --config-compare to use a snapshot from another target",
    )
    parser.add_argument("--snmp-community", default="public")
    parser.add_argument("--snmp-version", choices=("1", "2c"), default="1")
    parser.add_argument("--snmp-port", type=int, default=161)
    parser.add_argument("--snmp-timeout", type=float, default=1.5)
    parser.add_argument("--snmp-retries", type=int, default=2)
    args = parser.parse_args(argv)

    def run_discovery():
        return discover(
            timeout=args.discover_timeout,
            community=args.snmp_community,
            subnet=args.discover_subnet,
            use_wsd=not args.discover_no_wsd,
        )

    if args.check_update:
        if any(
            (
                args.host,
                args.device,
                args.usb,
                args.list_usb,
                args.usb_scan_info,
                args.usb_scan_capture,
                args.discover,
                args.web,
                args.gui,
                args.scan,
                args.snmp,
                args.push_scan,
                args.push_scan_listen,
                args.config,
                args.wifi_status,
                args.wifi_scan,
                args.wifi_connect,
                args.raw,
                args.watch is not None,
                args.count,
            )
        ):
            parser.error("--check-update can only be combined with --json")
        try:
            checker = UpdateChecker(
                url=os.environ.get("KYOCERA_UPDATE_URL", DEFAULT_UPDATE_URL)
            )
            update_result = checker.check(force=True)
        except UpdateCheckError as exc:
            print(f"Update check failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(
                json.dumps(
                    update_result.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"Current version: {update_result.current_version}")
            print(f"Latest version: {update_result.latest_version}")
            print(
                "Update available: "
                + ("yes" if update_result.update_available else "no")
            )
            print(f"Release: {update_result.release_url}")
        return 0

    if args.list_usb:
        printers = merge_usb_printers(
            discover_usb_printers(), discover_libusb_printers()
        )
        if args.json:
            print(
                json.dumps(
                    [printer.to_dict() for printer in printers],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for printer in printers:
                identity = (
                    f"{printer.vendor_id:04x}:{printer.product_id:04x}"
                    if printer.vendor_id is not None
                    and printer.product_id is not None
                    else "unknown"
                )
                description = " ".join(
                    value
                    for value in (printer.manufacturer, printer.product)
                    if value
                )
                print(f"{printer.device}\t{identity}\t{description}".rstrip())
        if not printers:
            print("no USB printer devices found", file=sys.stderr)
        return 0 if printers else 2

    if args.discover:
        if args.host or args.device or args.usb or args.web or args.gui:
            parser.error(
                "--discover cannot be combined with "
                "--host/--device/--usb/--web/--gui"
            )
        try:
            printers = run_discovery()
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(
                json.dumps(
                    [printer.to_dict() for printer in printers],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for printer in printers:
                fields = [
                    printer.address,
                    printer.model or "unknown",
                    printer.serial or "-",
                    printer.firmware or "-",
                    ",".join(printer.sources),
                ]
                print("\t".join(fields))
        if not printers:
            print("no printers found", file=sys.stderr)
        return 0 if printers else 1

    if not (
        args.host
        or args.device
        or args.usb
        or args.usb_scan_info
    ) and not (
        args.web or args.gui
    ):
        parser.error("one of --host, --device or --usb is required")
    if args.usb_scan_info and any(
        (
            args.host,
            args.device,
            args.usb,
            args.usb_scan_capture,
            args.web,
            args.gui,
            args.config,
            args.scan,
            args.push_scan,
            args.push_scan_listen,
            args.wifi_status,
            args.wifi_scan,
            args.wifi_connect,
        )
    ):
        parser.error("--usb-scan-info must be used alone")
    if args.usb_scan_capture is not None:
        if not args.usb:
            parser.error("--usb-scan-capture requires --usb")
        if any(
            (
                args.host,
                args.device,
                args.web,
                args.gui,
                args.config,
                args.scan,
                args.push_scan,
                args.push_scan_listen,
                args.wifi_status,
                args.wifi_scan,
                args.wifi_connect,
                args.watch is not None,
                args.count,
                args.raw,
            )
        ):
            parser.error(
                "USB scan capture cannot be combined with other modes"
            )
    if args.snmp and args.usb:
        parser.error("--snmp cannot be combined with --usb")
    if args.snmp and not args.host:
        parser.error("--snmp requires --host")
    if args.push_scan and args.push_scan_listen:
        parser.error("--push-scan and --push-scan-listen are mutually exclusive")
    if args.push_scan_run and not args.push_scan_listen:
        parser.error("--push-scan-run requires --push-scan-listen")
    if bool(args.wifi_status or args.wifi_scan or args.wifi_connect) and any(
        (
            args.config,
            args.scan,
            args.scan_output is not None,
            args.push_scan,
            args.push_scan_listen,
            args.web,
            args.gui,
            args.raw,
            args.watch is not None,
            args.count,
        )
    ):
        parser.error("Wi-Fi operations cannot be combined with other modes")
    if args.wifi_connect:
        if args.wifi_security is None:
            parser.error("--wifi-connect requires --wifi-security")
        if args.wifi_wep_index < 0:
            parser.error("--wifi-wep-index must be non-negative")
        if args.wifi_scan_timeout <= 0 or args.wifi_connect_timeout <= 0:
            parser.error("Wi-Fi timeouts must be positive")
    elif any(
        (
            args.wifi_security is not None,
            args.wifi_bssid,
            args.wifi_wep_index,
            args.wifi_connect_timeout != 25.0,
        )
    ):
        parser.error(
            "--wifi-security/--wifi-bssid/--wifi-wep-index/"
            "--wifi-connect-timeout require --wifi-connect"
        )
    if args.wifi_scan_timeout <= 0:
        parser.error("--wifi-scan-timeout must be positive")
    if args.wifi_scan_timeout != 20.0 and not (
        args.wifi_scan or args.wifi_connect
    ):
        parser.error("--wifi-scan-timeout requires --wifi-scan")
    if args.push_scan or args.push_scan_listen:
        if not args.host:
            parser.error("Push Scan inspection requires --host")
        if args.snmp:
            parser.error("Push Scan inspection cannot be combined with --snmp")
        if any(
            (
                args.device,
                args.usb,
                args.config,
                args.web,
                args.gui,
                args.scan,
                args.scan_output is not None,
                args.watch is not None,
                args.count,
                args.raw,
            )
        ):
            parser.error(
                "Push Scan inspection cannot be combined with other device modes"
            )
    if not args.push_scan_listen and (
        args.push_scan_poll_interval != 2.0
        or args.push_scan_max_polls != 0
    ):
        parser.error(
            "--push-scan-poll-interval/--push-scan-max-polls require "
            "--push-scan-listen"
        )
    if args.push_scan_listen:
        if args.push_scan_poll_interval < 0:
            parser.error("--push-scan-poll-interval must be non-negative")
        if args.push_scan_max_polls < 0:
            parser.error("--push-scan-max-polls must be non-negative")
    if args.config and (
        args.web
        or args.gui
        or args.watch is not None
        or args.count
        or args.raw
    ):
        parser.error(
            "--config cannot be combined with --web, --gui, "
            "--watch, --count or --raw"
        )
    if args.config and args.snmp and (args.device or args.usb):
        parser.error("--config --snmp requires --host")
    config_snapshot_modes = (
        args.config_save
        or args.config_compare
        or args.config_candidates
        or args.config_audit_safe
        or args.config_plan
        or args.config_apply
    )
    if config_snapshot_modes and not args.config:
        parser.error(
            "--config-save/--config-compare/--config-candidates/"
            "--config-audit-safe/--config-plan/--config-apply require --config"
        )
    if args.config_candidates and any(
        (
            args.config_save,
            args.config_compare,
            args.config_plan,
            args.config_apply,
            args.config_audit_safe,
        )
    ):
        parser.error(
            "--config-candidates cannot be combined with other config modes"
        )
    if args.config_save and args.config_compare:
        parser.error("--config-save and --config-compare are mutually exclusive")
    if args.config_audit_safe and any(
        (
            args.config_save,
            args.config_compare,
            args.config_candidates,
            args.config_plan,
            args.config_apply,
        )
    ):
        parser.error("--config-audit-safe cannot be combined with other config modes")
    if args.config_plan and (args.config_save or args.config_compare):
        parser.error("--config-plan cannot be combined with save/compare")
    if args.config_apply and (
        args.config_save or args.config_compare or args.config_plan
    ):
        parser.error("--config-apply cannot be combined with other config modes")
    if bool(args.config_plan or args.config_apply) != bool(args.config_set):
        parser.error("--config-plan/--config-apply require --config-set")
    if bool(args.config_apply) != bool(args.config_confirm):
        parser.error("--config-apply and --config-confirm must be used together")
    if args.config_apply and not args.snmp:
        parser.error("--config-apply currently requires --snmp")
    if args.config_apply and args.config_snmp_version != "2c":
        parser.error("--config-apply requires --config-snmp-version 2c")
    if args.config_audit_safe and not args.snmp:
        parser.error("--config-audit-safe requires --snmp")
    if args.config_audit_safe and args.config_snmp_version != "2c":
        parser.error("--config-audit-safe requires --config-snmp-version 2c")
    if args.config_force and not args.config_save:
        parser.error("--config-force requires --config-save")
    if args.config_allow_target_mismatch and not args.config_compare:
        parser.error("--config-allow-target-mismatch requires --config-compare")
    if (args.web or args.gui) and (
        args.watch is not None or args.count or args.raw or args.json
    ):
        parser.error(
            "--web/--gui cannot be combined with --watch, --count, --raw "
            "or --json"
        )
    if args.scan:
        if not args.host:
            parser.error("--scan requires --host")
        if args.device or args.usb or args.snmp:
            parser.error("--scan cannot be combined with USB or --snmp")
        if args.config or args.web or args.gui:
            parser.error("--scan cannot be combined with config or Web/GUI modes")
        if args.watch is not None or args.count or args.raw:
            parser.error("--scan cannot be combined with watch/count/raw")
    elif args.scan_output is not None:
        parser.error("--scan-output requires --scan")
    if args.usb:
        try:
            printers = merge_usb_printers(
                discover_usb_printers(), discover_libusb_printers()
            )
            args.device = select_usb_printer(printers).device
        except UsbError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.usb_scan_info:
        try:
            result = probe_scanner()
        except (UsbScanError, UsbError, OSError, TimeoutError, ValueError) as exc:
            print(f"USB scanner probe failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            info = result["machine_info"]["raw"]
            print(f"USB scanner: {result['vendor_id']}:{result['product_id']}")
            print(f"model code: {result['model_code']}")
            print(f"version: {result['version']}")
            for name, value in info.items():
                print(f"{name}: {value}")
            print("image capture: not implemented")
        return 0

    if args.usb_scan_capture is not None:
        try:
            parameters = usb_scan_parameters_from_cli(args)
            with UsbScannerControl() as scanner:
                scanner.connect()
                scanner.machine_info()
                scanner.version()
                page = scanner.capture_page(
                    parameters,
                    max_bytes=args.scan_max_response_bytes,
                    max_seconds=args.scan_timeout,
                )
            decoded = decode_raw(page.raw)
            stem = args.usb_scan_capture.stem or "usb-scan"
            artifacts = export_pages(
                [decoded],
                raw_pages=[page.raw],
                output_format=args.scan_format,
                output_stem=stem,
                resolution=args.scan_resolution,
            )
            scan_result = ScanResult(
                device="usb:0482:0d51",
                endpoint="usb:vendor-scanner",
                operation_id="usb-recovered-scan",
                pages=1,
                requested_device_format="RAW",
                effective_device_format="RAW",
                outputs=artifacts,
                close_result="disconnected",
                close_error=None,
            )
            paths = write_outputs(scan_result, args.usb_scan_capture)
        except (
            OSError,
            RawScanError,
            TimeoutError,
            UsbScanError,
            ValueError,
        ) as exc:
            print(f"USB scan capture failed: {exc}", file=sys.stderr)
            return 2
        payload = {
            "device": scan_result.device,
            "transport": scan_result.endpoint,
            "source": page.scan_ack.source,
            "terminator": page.terminator,
            "raw_bytes": len(page.raw),
            "width": decoded.width,
            "height": decoded.height,
            "outputs": [
                {
                    **artifact.metadata(),
                    "path": str(path),
                }
                for artifact, path in zip(artifacts, paths, strict=True)
            ],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"USB scan: {decoded.width}x{decoded.height}, "
                f"{len(page.raw)} raw bytes"
            )
            for path in paths:
                print(path)
        return 0

    if args.wifi_status or args.wifi_scan or args.wifi_connect:
        try:
            with open_channel(
                host=args.host,
                device=args.device,
                port=args.port,
            ) as channel:
                if args.wifi_status:
                    result = read_wifi_status(
                        channel,
                        timeout=args.timeout,
                        idle=args.idle,
                    )
                    if args.json:
                        print(
                            json.dumps(result, ensure_ascii=False, indent=2)
                        )
                    else:
                        print(
                            "Wi-Fi: {state}  SSID: {ssid}  "
                            "Security: {security_name}  "
                            "RSSI: {rssi} dBm  Channel: {channel}".format(
                                state=(
                                    "connected"
                                    if result["connected"]
                                    else "not connected"
                                ),
                                **result,
                            )
                        )
                elif args.wifi_scan:
                    access_points = scan_access_points(
                        channel,
                        timeout=args.timeout,
                        idle=args.idle,
                        scan_timeout=args.wifi_scan_timeout,
                    )
                    if args.json:
                        print(
                            json.dumps(
                                [
                                    point.to_dict()
                                    for point in access_points
                                ],
                                ensure_ascii=False,
                                indent=2,
                            )
                        )
                    else:
                        for point in access_points:
                            print(
                                f"{point.index}\t{point.ssid}\t"
                                f"{point.security_name}\t"
                                f"{point.rssi if point.rssi is not None else '-'}"
                                f"\t{point.bssid}"
                            )
                else:
                    secret = os.environ.get(args.wifi_password_env)
                    if args.wifi_security in (1, 2, 3, 4) and not secret:
                        if not sys.stdin.isatty():
                            raise WifiError(
                                f"set {args.wifi_password_env} or run "
                                "interactively to enter the Wi-Fi secret"
                            )
                        secret = getpass.getpass("Wi-Fi secret: ")
                    result = connect_access_point(
                        channel,
                        ssid=args.wifi_connect,
                        security=args.wifi_security,
                        password=secret,
                        bssid=args.wifi_bssid,
                        wep_index=args.wifi_wep_index,
                        timeout=args.timeout,
                        idle=args.idle,
                        connect_timeout=args.wifi_connect_timeout,
                        on_progress=(
                            lambda message: print(message, file=sys.stderr)
                            if not args.json
                            else None
                        ),
                    )
                    if args.json:
                        print(
                            json.dumps(result, ensure_ascii=False, indent=2)
                        )
                    else:
                        print(
                            f"connected to {result['ssid']} using "
                            f"{result['security_name']}"
                        )
        except (
            WifiError,
            PjlError,
            OSError,
            TimeoutError,
            ValueError,
        ) as exc:
            print(f"Wi-Fi operation failed: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.push_scan:
        try:
            push_scan_result = read_push_scan(
                args.host,
                community=args.snmp_community,
                version=args.snmp_version,
                port=args.snmp_port,
                timeout=args.snmp_timeout,
                retries=args.snmp_retries,
            )
        except (BerError, OSError, TimeoutError, ValueError) as exc:
            print(f"Push Scan read failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(
                json.dumps(
                    push_scan_result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(format_push_scan(push_scan_result))
        return 0

    if args.push_scan_listen:
        def read_codes():
            return read_vendor_status_codes(
                args.host,
                community=args.snmp_community,
                version=args.snmp_version,
                port=args.snmp_port,
                timeout=args.snmp_timeout,
                retries=args.snmp_retries,
            )

        settings_store = None
        scan_manager = None
        if args.push_scan_run:
            settings_store = SettingsStore()
            scan_manager = ScanJobManager()
            try:
                settings_store.load()
            except SettingsError as exc:
                print(f"Push Scan settings failed: {exc}", file=sys.stderr)
                return 2
        max_polls = args.push_scan_max_polls or None
        if not args.json:
            print(
                f"listening for Push Scan status codes on {args.host}",
                file=sys.stderr,
                flush=True,
            )
        try:
            for poll, codes, event in iter_push_scan_events(
                args.host,
                read_codes,
                poll_interval=args.push_scan_poll_interval,
                max_polls=max_polls,
            ):
                if event is not None:
                    payload = dict(event)
                    if (
                        settings_store is not None
                        and scan_manager is not None
                    ):
                        try:
                            push_state = read_push_scan(
                                args.host,
                                community=args.snmp_community,
                                version=args.snmp_version,
                                port=args.snmp_port,
                                timeout=args.snmp_timeout,
                                retries=args.snmp_retries,
                            )
                            execution = execute_push_scan_event(
                                event,
                                settings_store.load(),
                                scan_manager,
                                push_state=push_state,
                            )
                        except (
                            BerError,
                            OSError,
                            TimeoutError,
                            SettingsError,
                            ValueError,
                        ) as exc:
                            execution = {
                                "mode": "local_preset_mapping",
                                "status": "readiness_error",
                                "error": str(exc),
                                "result_writeback": "not_attempted",
                            }
                        payload["execution_supported"] = True
                        payload["execution_state"] = execution["status"]
                        payload["local_execution"] = execution
                    if args.json:
                        print(
                            json.dumps(
                                payload,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    else:
                        print(
                            "Push Scan preset "
                            f"{event['preset_number']} requested "
                            f"(status {event['status_code']})"
                        )
                        if "local_execution" in payload:
                            print(
                                "Local preset execution: "
                                f"{payload['local_execution']['status']}"
                            )
                elif not args.json:
                    current = codes[0] if codes else "unavailable"
                    print(
                        f"poll {poll}: current status {current}",
                        file=sys.stderr,
                    )
        except KeyboardInterrupt:
            return 0
        except (BerError, OSError, TimeoutError, ValueError) as exc:
            print(f"Push Scan listener failed: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.scan:
        options = ScanOptions(
            color=args.scan_color,
            resolution=args.scan_resolution,
            original_image=args.scan_original_image,
            duplex_mode=args.scan_duplex,
            original_placement=args.scan_original_placement,
            continuous_scan_mode=args.scan_continuous,
            output_format=args.scan_format,
            max_pages=args.scan_max_pages,
            max_polls=args.scan_max_polls,
            poll_interval=args.scan_poll_interval,
            timeout=args.scan_timeout,
            max_response_bytes=args.scan_max_response_bytes,
            device_file_format=args.scan_device_format,
            operation_id=args.scan_operation_id,
            retrieve_only=args.scan_retrieve_only,
            https=args.scan_https,
            port=args.scan_port,
            insecure=args.scan_insecure,
        )
        try:
            result = scan_device(args.host, options)
            destination = args.scan_output or Path.cwd()
            paths = write_outputs(result, destination)
        except ScanError as exc:
            if args.json:
                print(
                    json.dumps(
                        {"ok": False, **exc.to_dict()},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(
                    f"scan failed at {exc.stage}: {exc.message}",
                    file=sys.stderr,
                )
            return 1
        except (OSError, ValueError) as exc:
            print(f"scan failed: {exc}", file=sys.stderr)
            return 2
        payload = result.metadata()
        payload["ok"] = True
        for output, path in zip(payload["outputs"], paths):
            output["path"] = str(path)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"scanned {result.pages} page(s) from {result.device} "
                f"using device format {result.effective_device_format or 'unknown'}"
            )
            for artifact, path in zip(result.outputs, paths):
                print(f"{artifact.kind}\t{artifact.size}\t{path}")
            if result.close_error:
                print(
                    f"close_session warning: {result.close_error}",
                    file=sys.stderr,
                )
        return 0

    if args.config:
        try:
            if args.snmp:
                records = collect_config_snmp(
                    args.host,
                    community=args.snmp_community,
                    version=args.config_snmp_version,
                    port=args.snmp_port,
                    timeout=args.snmp_timeout,
                    retries=args.snmp_retries,
                )
                transport = "snmp"
            else:
                with open_channel(
                    host=args.host, device=args.device, port=args.port
                ) as channel:
                    records = collect_config(
                        channel, timeout=args.timeout, idle=args.idle
                    )
                transport = "pjl"
        except (OSError, PjlError, TimeoutError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        read_count = sum(1 for record in records if record.get("status") == 0)
        target = args.host or args.device
        saved_path = None
        comparison = None
        write_plan = None
        write_execution = None
        safe_audit_plan = None
        safe_audit = None
        candidate_report = None
        if config_snapshot_modes:
            try:
                snapshot = build_config_snapshot(
                    records,
                    transport=transport,
                    target=target,
                )
                if args.config_save:
                    saved_path = save_config_snapshot(
                        args.config_save,
                        snapshot,
                        overwrite=args.config_force,
                    )
                elif args.config_compare:
                    baseline = load_config_snapshot(args.config_compare)
                    comparison = compare_config_snapshots(
                        baseline,
                        snapshot,
                        allow_target_mismatch=args.config_allow_target_mismatch,
                    )
                elif args.config_candidates:
                    candidate_report = build_config_candidate_report(snapshot)
                elif args.config_audit_safe:
                    baseline = load_config_snapshot(args.config_audit_safe)
                    safe_audit_plan = build_safe_audit_plan(baseline, snapshot)
                    client = SnmpClient(
                        args.host,
                        community=args.snmp_community,
                        version="2c",
                        port=args.snmp_port,
                        timeout=args.snmp_timeout,
                        retries=args.snmp_retries,
                    )
                    safe_audit = execute_safe_audit(client, safe_audit_plan)
                elif args.config_plan:
                    baseline = load_config_snapshot(args.config_plan)
                    write_plan = build_config_write_plan(
                        baseline,
                        snapshot,
                        args.config_set,
                    )
                else:
                    baseline = load_config_snapshot(args.config_apply)
                    write_plan = build_config_write_plan(
                        baseline,
                        snapshot,
                        args.config_set,
                    )
                    client = SnmpClient(
                        args.host,
                        community=args.snmp_community,
                        version="2c",
                        port=args.snmp_port,
                        timeout=args.snmp_timeout,
                        retries=args.snmp_retries,
                    )
                    write_execution = execute_authorized_config_experiment(
                        client,
                        write_plan,
                        args.config_confirm,
                    )
            except ConfigSnapshotError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            except ConfigWritePlanError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            except ConfigCandidateError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            except ConfigWriteAuditError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            except (
                ConfigWriteExecutionError,
                BerError,
                OSError,
                TimeoutError,
                ValueError,
            ) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
        if args.json:
            payload = {
                "source": "clienttool-1.4.11.2 config objects",
                "transport": transport,
                "read": read_count,
                "total": len(records),
            }
            if candidate_report is None:
                payload["objects"] = records
            if comparison is not None:
                payload["baseline"] = {
                    "created_at": baseline["created_at"],
                    "target": baseline["target"],
                    "transport": baseline["transport"],
                }
                payload["comparison"] = comparison
            if write_plan is not None:
                payload["write_plan"] = write_plan
            if write_execution is not None:
                payload["write_execution"] = write_execution
            if safe_audit_plan is not None:
                payload["safe_audit_plan"] = safe_audit_plan
            if safe_audit is not None:
                payload["safe_audit"] = safe_audit
            if candidate_report is not None:
                payload["candidate_report"] = candidate_report
            print(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif safe_audit is not None:
            print("safe configuration write audit")
            print(f"target: {safe_audit['target']} (snmp)")
            print(
                f"planned: {safe_audit['planned']}; "
                f"attempted: {safe_audit['attempted']}; "
                f"successful: {safe_audit['successful']}; "
                f"restored: {safe_audit['restored']}"
            )
            for result in safe_audit["results"]:
                if result["status"] in (
                    "success",
                    "target_rejected_or_unverified",
                ):
                    print(
                        f"{result['item_id']:3d}\t{result['label']}\t"
                        f"{result['before']} -> {result['target']} -> "
                        f"{result['verify_restore']['observed']}\t"
                        f"{result['status']}"
                    )
                else:
                    print(
                        f"{result['item_id']:3d}\t{result['label']}\t"
                        f"{result['status']}"
                    )
            print(f"status: {safe_audit['status']}")
        elif write_execution is not None:
            print(
                "configuration write execution: "
                f"{write_execution['label']} OFF -> ON -> OFF"
            )
            print(f"target: {write_execution['target']} (snmp)")
            print(f"object OID: {write_execution['oid']}")
            print(f"status: {write_execution['status']}")
            for label, key in (
                ("set ON", "set_on"),
                ("verify ON", "verify_on"),
                ("set OFF", "set_off"),
                ("verify OFF", "verify_off"),
            ):
                step = write_execution[key]
                details = ", ".join(
                    f"{name}={value!r}"
                    for name, value in step.items()
                    if value is not None
                )
                print(f"{label}: {details}")
        elif write_plan is not None:
            plan = write_plan
            print("configuration write plan (DRY RUN; no commands sent)")
            print(
                f"target: {plan['target']} ({plan['transport']})\n"
                f"object: {plan['object']['item_id']} "
                f"{plan['object']['label']} "
                f"[{plan['object']['absolute_oid']}]"
            )
            print(
                "transition: "
                f"{plan['before']['display']} -> "
                f"{plan['requested']['display']}"
            )
            print(
                f"rollback: {plan['rollback']['display']} "
                f"({plan['rollback']['value']})"
            )
            print(f"PJL preview: {plan['commands']['pjl_line']}")
            print(
                "SNMP preview: SET "
                f"{plan['commands']['snmp_set']['oid']} "
                f"Integer {plan['commands']['snmp_set']['value']}"
            )
            review = plan["review"]
            blockers = review["blockers"]
            print(
                "review: "
                + (
                    "plan preconditions valid"
                    if review["plan_preconditions_valid"]
                    else "blocked"
                )
            )
            for blocker in blockers:
                print(f"plan blocker: {blocker}")
            if not review["executor_supported"]:
                print("executor: unavailable for this field")
            if plan["execution"]["allowed"]:
                print(
                    "execution: authorized with confirmation token "
                    f"({plan['execution']['authorization_scope']})"
                )
            else:
                print(
                    "execution: blocked "
                    f"({', '.join(plan['execution']['blockers'])})"
                )
            print(
                "confirmation token: "
                f"{plan['confirmation']['algorithm']}:"
                f"{plan['confirmation']['token']}"
            )
        elif candidate_report is not None:
            print(
                "configuration write candidates "
                "(READ ONLY; no commands sent)"
            )
            print(
                f"target: {candidate_report['target']} "
                f"({candidate_report['transport']})"
            )
            for candidate in candidate_report["candidates"]:
                observed = candidate["observed"]
                value = observed.get("display")
                if value is None:
                    value = observed.get("raw_value")
                if value is None:
                    value = "unreadable"
                print(
                    f"candidate: {candidate['item_id']} "
                    f"{candidate['label']} "
                    f"[{candidate['absolute_oid']}]"
                )
                print(f"observed: {value!r}")
                print(
                    "mapping: "
                    f"{candidate['evidence']['mapping_confidence']} "
                    f"(control {candidate['evidence']['ui_control']}, "
                    f"offset {candidate['evidence']['model_offset']})"
                )
                print(
                    "current read: "
                    + (
                        "valid"
                        if candidate["review"]["current_read_valid"]
                        else "blocked"
                    )
                )
                for blocker in candidate["write"]["blockers"]:
                    print(f"write blocker: {blocker}")
                print("write: not authorized")
            recommendation = candidate_report["recommendation"]
            print(
                "recommendation: "
                f"{recommendation['status']} "
                f"(item {recommendation['item_id']})"
            )
            print(recommendation["note"])
        elif comparison is not None:
            for change in (
                comparison["changes"]
                + comparison["volatile_changes"]
                + comparison["read_status_changes"]
            ):
                before = change["before"]
                after = change["after"]
                if change["sensitive"]:
                    before_value = after_value = "<redacted>"
                else:
                    before_value = before.get("display")
                    if before_value is None:
                        before_value = before.get("error", "")
                    after_value = after.get("display")
                    if after_value is None:
                        after_value = after.get("error", "")
                print(
                    f"{change['item_id']:3d}\t{change['label']}\t"
                    f"{before_value!r} -> {after_value!r}"
                )
            if not (
                comparison["changed"]
                or comparison["volatile_changed"]
                or comparison["read_status_changed"]
            ):
                print("no configuration changes")
        else:
            for record in records:
                label = (
                    record.get("label")
                    or record.get("vendor_name")
                    or record.get("pjl_object")
                    or record.get("absolute_oid")
                    or record["oid"]
                )
                value = record.get("display")
                if value is None:
                    value = record.get("error", "")
                status = record.get("status", "-")
                print(f"{record['item_id']:3d}\t{status}\t{label}\t{value}")
        print(f"read {read_count}/{len(records)}", file=sys.stderr)
        if saved_path is not None:
            print(
                f"saved configuration snapshot to {saved_path} (mode 0600); "
                "the file may contain communities, SSIDs, or other site data",
                file=sys.stderr,
            )
        if comparison is not None:
            print(
                f"configuration comparison: {comparison['changed']} value changes, "
                f"{comparison['volatile_changed']} volatile observations, "
                f"{comparison['read_status_changed']} read-status changes, "
                f"{comparison['unchanged']} unchanged",
                file=sys.stderr,
            )
            return (
                1
                if comparison["changed"] or comparison["read_status_changed"]
                else 0
            )
        if write_plan is not None and write_execution is None:
            print(
                "write plan generated; no write command was sent",
                file=sys.stderr,
            )
            return (
                0
                if write_plan["review"]["plan_preconditions_valid"]
                else 1
            )
        if safe_audit is not None:
            print(
                f"safe configuration audit finished: {safe_audit['status']}",
                file=sys.stderr,
            )
            return 0 if safe_audit["status"] == "completed" else 1
        if write_execution is not None:
            print(
                f"write execution finished: {write_execution['status']}",
                file=sys.stderr,
            )
            return 0 if write_execution["status"] == "success" else 1
        return 0 if read_count else 1

    if args.web or args.gui:
        explicit_usb_only = bool(args.device or args.usb)
        automatic_usb_printers = []
        if not (args.host or args.device or args.usb):
            try:
                automatic_usb_printers = merge_usb_printers(
                    discover_usb_printers(), discover_libusb_printers()
                )
            except UsbError:
                automatic_usb_printers = []
        automatic_usb_key = (
            automatic_usb_printers[0].device
            if len(automatic_usb_printers) == 1
            else None
        )
        default_key = args.host or args.device or automatic_usb_key

        usb_access_guard = threading.Lock()
        usb_access_locks: dict[str, threading.RLock] = {}

        def usb_access_lock(key: str):
            with usb_access_guard:
                return usb_access_locks.setdefault(key, threading.RLock())

        def collect_host(key: str) -> PrinterSnapshot:
            if args.snmp:
                return collect_snmp_snapshot(
                    key,
                    community=args.snmp_community,
                    version=args.snmp_version,
                    port=args.snmp_port,
                    timeout=args.snmp_timeout,
                    retries=args.snmp_retries,
                )
            if key.startswith("libusb:") or key.startswith("/dev/"):
                with usb_access_lock(key):
                    _, snapshot = collect(
                        None,
                        key,
                        args.port,
                        args.timeout,
                        args.idle,
                        USB_QUERY_SEQUENCE,
                    )
                return snapshot
            _, snapshot = collect(
                key,
                None,
                args.port,
                args.timeout,
                args.idle,
                QUERY_SEQUENCE,
            )
            return snapshot

        registry = DeviceRegistry(collect_host, default_key)
        for printer in automatic_usb_printers:
            registry.allow(printer.device)
        config_workbench = None
        push_scan_reader = None

        @contextmanager
        def open_web_wifi_channel(target: str):
            if target.startswith("libusb:") or target.startswith("/dev/"):
                with usb_access_lock(target):
                    with open_channel(device=target, port=args.port) as channel:
                        yield channel
                return
            with open_channel(host=target, port=args.port) as channel:
                yield channel

        wifi_workbench = WifiWorkbench(
            open_web_wifi_channel,
            timeout=args.timeout,
            idle=args.idle,
            scan_timeout=20.0,
            connect_timeout=25.0,
        )

        def is_usb_target(key: str) -> bool:
            return key.startswith("libusb:") or key.startswith("/dev/")

        def read_web_configuration(
            key: str,
            item_ids: tuple[int, ...] | None = None,
        ):
            if is_usb_target(key):
                with usb_access_lock(key):
                    with open_channel(device=key, port=args.port) as channel:
                        return collect_config(
                            channel,
                            timeout=args.timeout,
                            idle=args.idle,
                            item_ids=item_ids,
                        )
            return collect_config_snmp(
                key,
                community=args.snmp_community,
                version=args.config_snmp_version,
                port=args.snmp_port,
                timeout=args.snmp_timeout,
                retries=args.snmp_retries,
                item_ids=item_ids,
            )

        def write_web_configuration(key: str, oid: str, value: int):
            if is_usb_target(key):
                with usb_access_lock(key):
                    with open_channel(device=key, port=args.port) as channel:
                        return set_config_integer(
                            channel,
                            oid,
                            value,
                            timeout=args.timeout,
                            idle=args.idle,
                        )
            client = SnmpClient(
                key,
                community=args.snmp_community,
                version=args.config_snmp_version,
                port=args.snmp_port,
                timeout=args.snmp_timeout,
                retries=args.snmp_retries,
            )
            return client.set_integer(oid, value)

        config_workbench = ConfigWorkbench(
            read_web_configuration,
            scoped_reader=read_web_configuration,
            writer=write_web_configuration,
            transport=lambda key: (
                "pjl" if is_usb_target(key) else "snmp"
            ),
        )

        if not explicit_usb_only:
            def read_web_push_scan(key: str):
                if is_usb_target(key):
                    raise ValueError(
                        "Push Scan status requires a network connection"
                    )
                return read_push_scan(
                    key,
                    community=args.snmp_community,
                    version=args.config_snmp_version,
                    port=args.snmp_port,
                    timeout=args.snmp_timeout,
                    retries=args.snmp_retries,
                )

            push_scan_reader = read_web_push_scan
        discover_fn = (
            None if explicit_usb_only else run_discovery
        )
        if args.gui:
            from .gui import GuiUnavailable, run_gui

            try:
                run_gui(
                    registry,
                    discover_fn=discover_fn,
                    config_workbench=config_workbench,
                    push_scan_reader=push_scan_reader,
                    wifi_workbench=wifi_workbench,
                )
            except GuiUnavailable as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            except OSError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            return 0

        def announce(url: str) -> None:
            print(f"serving {url}", file=sys.stderr, flush=True)
            if args.web_open:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass

        try:
            run_server(
                registry,
                bind=args.web_bind,
                port=args.web_port,
                discover_fn=discover_fn,
                on_listen=announce,
                config_workbench=config_workbench,
                push_scan_reader=push_scan_reader,
                wifi_workbench=wifi_workbench,
            )
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    polls = 0
    previous: str | None = None
    while True:
        try:
            if args.snmp:
                raw, snapshot = collect_snmp(args)
            else:
                commands = (
                    USB_QUERY_SEQUENCE
                    if (args.usb or args.device)
                    else QUERY_SEQUENCE
                )
                raw, snapshot = collect(
                    args.host,
                    args.device,
                    args.port,
                    args.timeout,
                    args.idle,
                    commands,
                )
        except (OSError, PjlError, TimeoutError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if args.expect_model and snapshot.model != args.expect_model:
            print(
                f"error: expected model {args.expect_model!r}, got {snapshot.model!r}",
                file=sys.stderr,
            )
            return 4

        if args.raw:
            output = raw.decode("ascii", "replace")
        elif args.json:
            output = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2)
        else:
            output = format_snapshot(snapshot)

        if args.watch is None or output != previous:
            print(output, flush=True)
        previous = output
        polls += 1
        if args.watch is None or (args.count and polls >= args.count):
            break
        time.sleep(args.watch)

    if snapshot.normal is False:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
