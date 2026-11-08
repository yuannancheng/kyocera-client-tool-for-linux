import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from kyocera_monitor import cli
from kyocera_monitor.config import CONFIG, absolute_config_oid
from kyocera_monitor.config_web import ConfigWorkbenchError
from kyocera_monitor.discovery import DiscoveredPrinter
from kyocera_monitor.parser import PrinterSnapshot, Tray
from kyocera_monitor.preferences import SettingsStore
from kyocera_monitor.scan import ScanArtifact, ScanJobManager, ScanResult
from kyocera_monitor.usb import UsbPrinter
from kyocera_monitor.web import (
    DEVICE_HTML,
    OVERVIEW_HTML,
    DeviceRegistry,
    SnapshotCache,
    make_handler,
    normalize_host,
    reading_payload,
)


class FakeClock:
    def __init__(self, now: float = 100.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def snapshot() -> PrinterSnapshot:
    return PrinterSnapshot(
        model="MA2000w",
        serial="REDACTED",
        status_code=35078,
        toner_level=80,
        tray_status=[Tray(name="INTRAY1", status="OK", paper="A4")],
    )


class CacheTests(unittest.TestCase):
    def test_recent_result_is_reused(self):
        clock = FakeClock()
        calls = []

        def collect():
            calls.append(clock.now)
            return snapshot()

        cache = SnapshotCache(collect, min_interval=1.0, clock=clock)
        first = cache.read()
        clock.now += 0.4
        second = cache.read()
        self.assertEqual(len(calls), 1)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertIs(second.snapshot, first.snapshot)

    def test_result_is_refreshed_after_interval(self):
        clock = FakeClock()
        calls = []

        def collect():
            calls.append(clock.now)
            return snapshot()

        cache = SnapshotCache(collect, min_interval=1.0, clock=clock)
        cache.read()
        clock.now += 1.5
        second = cache.read()
        self.assertEqual(len(calls), 2)
        self.assertFalse(second.cached)

    def test_error_is_returned_without_raising(self):
        calls = []

        def collect():
            calls.append(1)
            raise OSError("printer offline")

        cache = SnapshotCache(collect, min_interval=1.0, clock=FakeClock())
        reading = cache.read()
        self.assertIsNone(reading.snapshot)
        self.assertIn("printer offline", reading.error)
        self.assertEqual(len(calls), 1)

    def test_collected_at_uses_wall_clock(self):
        cache = SnapshotCache(
            snapshot,
            min_interval=0,
            clock=FakeClock(100.0),
            wall_clock=lambda: 1_700_000_000.0,
        )
        reading = cache.read()
        self.assertEqual(reading.collected_at, 1_700_000_000.0)
        payload = reading_payload(reading, "192.168.0.220")
        self.assertTrue(payload["collected_at"].startswith("2023-"))


class PayloadTests(unittest.TestCase):
    def test_payload_contains_snapshot_and_timing(self):
        cache = SnapshotCache(snapshot, min_interval=0, clock=FakeClock())
        payload = reading_payload(cache.read(), "192.168.0.220")
        self.assertEqual(payload["device"], "192.168.0.220")
        self.assertEqual(payload["snapshot"]["model"], "MA2000w")
        self.assertEqual(payload["snapshot"]["status_code"], 35078)
        self.assertFalse(payload["cached"])
        self.assertIsNone(payload["error"])
        self.assertIn("collected_at", payload)
        self.assertIsInstance(payload["elapsed_ms"], int)

    def test_error_payload_has_no_snapshot(self):
        def broken():
            raise TimeoutError("no response")

        cache = SnapshotCache(broken, min_interval=0, clock=FakeClock())
        payload = reading_payload(cache.read())
        self.assertIsNone(payload["snapshot"])
        self.assertIn("no response", payload["error"])


class RegistryTests(unittest.TestCase):
    def test_unknown_host_is_rejected(self):
        registry = DeviceRegistry(
            lambda key: snapshot(), "192.168.0.1", min_interval=0
        )
        with self.assertRaises(KeyError):
            registry.read("192.168.0.9")

    def test_allowed_hosts_have_separate_caches(self):
        calls = []

        def factory(key):
            calls.append(key)
            return snapshot()

        registry = DeviceRegistry(factory, "192.168.0.1", min_interval=0)
        registry.allow("192.168.0.220")
        registry.read()
        registry.read("192.168.0.220")
        self.assertEqual(calls, ["192.168.0.1", "192.168.0.220"])

    def test_hosts_are_sorted_by_address(self):
        registry = DeviceRegistry(
            lambda key: snapshot(), "192.168.0.220", min_interval=0
        )
        registry.allow("192.168.0.5")
        self.assertEqual(registry.hosts(), ["192.168.0.5", "192.168.0.220"])

    def test_read_many_keeps_per_device_errors(self):
        def factory(key):
            if key == "192.168.0.9":
                raise OSError("offline")
            return snapshot()

        registry = DeviceRegistry(factory, "192.168.0.1", min_interval=0)
        registry.allow("192.168.0.9")
        results = registry.read_many(max_workers=2)
        self.assertEqual(sorted(results), ["192.168.0.1", "192.168.0.9"])
        self.assertEqual(results["192.168.0.1"].snapshot.model, "MA2000w")
        self.assertIn("offline", results["192.168.0.9"].error)

    def test_registry_can_start_without_a_default_device(self):
        registry = DeviceRegistry(lambda key: snapshot(), None, min_interval=0)
        self.assertEqual(registry.hosts(), [])
        with self.assertRaises(KeyError):
            registry.read()
        registry.add_host("192.168.0.220")
        self.assertEqual(registry.resolve(), "192.168.0.220")
        self.assertEqual(registry.read().snapshot.model, "MA2000w")

    def test_add_host_rejects_non_host_inputs(self):
        registry = DeviceRegistry(lambda key: snapshot(), None)
        for value in ("", "http://192.168.0.220", "/dev/usb/lp0",
                      "192.168.0.300", "printer:9100"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    registry.add_host(value)

    def test_add_host_normalizes_ipv4_and_hostnames(self):
        registry = DeviceRegistry(lambda key: snapshot(), None)
        self.assertEqual(registry.add_host(" 192.168.000.220 "),
                         "192.168.0.220")
        self.assertEqual(registry.add_host("Printer.Local"), "printer.local")


class PageTests(unittest.TestCase):
    def test_overview_fetches_devices_and_can_discover(self):
        self.assertIn("/api/devices", OVERVIEW_HTML)
        self.assertIn("/api/discover", OVERVIEW_HTML)
        self.assertIn("/device?host=", OVERVIEW_HTML)

    def test_device_page_fetches_status(self):
        self.assertIn("/api/status", DEVICE_HTML)
        self.assertIn("fetch(statusUrl()", DEVICE_HTML)

    def test_pages_use_toast_not_a_top_error_bar(self):
        for page in (OVERVIEW_HTML, DEVICE_HTML):
            self.assertIn('id="toasts"', page)
            self.assertIn("function showToast(", page)
            self.assertIn('role="status" aria-live="polite"', page)
            self.assertNotIn('id="error"', page)
            self.assertNotIn('class="error"', page)

    def test_device_page_shows_counters_and_settings(self):
        for element_id in ("lifetime", "scan", "drum", "config-mode-note"):
            self.assertIn(f'id="{element_id}"', DEVICE_HTML)
        self.assertIn("kgetobj_known", DEVICE_HTML)

    def test_device_page_has_integrated_scan_workflow(self):
        for element_id in (
            "scan-form",
            "scan-color",
            "scan-resolution",
            "scan-original-image",
            "scan-pages",
            "scan-format",
            "scan-progress",
            "scan-downloads",
        ):
            self.assertIn(f'id="{element_id}"', DEVICE_HTML)
        self.assertIn("/api/scans", DEVICE_HTML)
        self.assertIn('value="png"', DEVICE_HTML)
        self.assertIn('value="pdf"', DEVICE_HTML)
        for value in (
            "jpeg",
            "tiff",
            "high_compression_pdf",
            "xps",
        ):
            self.assertIn(f'value="{value}"', DEVICE_HTML)

    def test_scan_result_contrast_is_theme_safe(self):
        for token in (
            ".progress.success",
            ".progress.warning",
            ".progress.failure",
            ".progress.success { display: block; background: #e5f4e7; color: #174c22;",
            ".progress.success { background: #1d3523; color: #d3f2d8;",
        ):
            self.assertIn(token, DEVICE_HTML)
        self.assertNotIn("progress.style.background", DEVICE_HTML)
        self.assertIn(
            'setScanStatus(message, result.close_error ? "warning" : "success")',
            DEVICE_HTML,
        )

    def test_status_pills_have_explicit_light_and_dark_contrast(self):
        for page in (OVERVIEW_HTML, DEVICE_HTML):
            self.assertIn(
                "background: #d8dee6; color: #1b1f24;",
                page,
            )
            self.assertIn(
                ".pill { background: #303842; color: #e7ebef; }",
                page,
            )

    def test_device_page_has_native_download_bridge(self):
        self.assertIn('messageHandlers.kyoceraDownload', DEVICE_HTML)
        self.assertIn("link.addEventListener(\"click\"", DEVICE_HTML)
        self.assertIn('setScanStatus("正在下载 "', DEVICE_HTML)

    def test_device_page_has_wifi_status_scan_and_connect(self):
        for element_id in (
            "wifi-settings",
            "wifi-scan",
            "wifi-ap-select",
            "wifi-ssid",
            "wifi-security",
            "wifi-password",
            "wifi-connect-confirm",
            "wifi-connect",
        ):
            self.assertIn(f'id="{element_id}"', DEVICE_HTML)
        self.assertIn("/api/wifi/scan", DEVICE_HTML)
        self.assertIn("/api/wifi/connect", DEVICE_HTML)
        self.assertNotIn("/api/wifi/status", DEVICE_HTML)
        self.assertGreater(
            DEVICE_HTML.index('id="wifi-settings"'),
            DEVICE_HTML.index('id="config-category-title"'),
        )
        self.assertLess(
            DEVICE_HTML.index('id="wifi-settings"'),
            DEVICE_HTML.index('id="config-objects"'),
        )
        self.assertIn("selectedConfigCategory !== \"wifi\"", DEVICE_HTML)

    def test_scan_section_does_not_repeat_english_device_settings(self):
        self.assertNotIn('id="settings"', DEVICE_HTML)
        self.assertNotIn("Auto error clear: ${autoClear}", DEVICE_HTML)
        self.assertNotIn("Form feed timeout: ${formFeed} s", DEVICE_HTML)
        self.assertIn('"Auto error clear": "自动错误清除"', DEVICE_HTML)
        self.assertIn('"Form feed timeout": "送纸超时"', DEVICE_HTML)

    def test_device_page_has_presets_folder_and_settings(self):
        for element_id in (
            "preset-select",
            "preset-name",
            "preset-save",
            "preset-delete",
            "scan-directory",
            "save-folder",
            "settings-save",
        ):
            self.assertIn(f'id="{element_id}"', DEVICE_HTML)
        self.assertIn("/api/settings", DEVICE_HTML)

    def test_device_page_has_reviewed_configuration_workflow(self):
        for element_id in (
            "config-read",
            "config-baseline-save",
            "config-baseline-compare",
            "config-status-grid",
            "config-edit-items",
            "config-edit-status",
            "config-objects",
            "config-categories",
            "config-category-title",
            "config-category-description",
        ):
            self.assertIn(f'id="{element_id}"', DEVICE_HTML)
        self.assertIn("/api/config/apply", DEVICE_HTML)
        self.assertIn("/api/config/categories", DEVICE_HTML)
        self.assertIn("category: selectedConfigCategory", DEVICE_HTML)
        self.assertIn("只访问当前分区", DEVICE_HTML)
        self.assertIn(
            "grid-template-columns: minmax(0, 1fr) max-content",
            DEVICE_HTML,
        )
        self.assertIn("justify-self: end; align-self: start", DEVICE_HTML)
        self.assertIn("无法连接本机后台服务", DEVICE_HTML)
        for removed in (
            "安全回滚实验",
            "OFF → ON → OFF",
            "/api/config/plan",
            'id="config-write-item"',
            'id="config-plan"',
            'id="config-authorize"',
        ):
            self.assertNotIn(removed, DEVICE_HTML)

    def test_pages_are_self_contained(self):
        for page in (OVERVIEW_HTML, DEVICE_HTML):
            self.assertNotIn("http://", page)
            self.assertNotIn("https://", page)

    def test_overview_has_manual_device_form(self):
        self.assertIn('id="add"', OVERVIEW_HTML)
        self.assertIn('id="host"', OVERVIEW_HTML)
        self.assertIn('method: "POST"', OVERVIEW_HTML)
        self.assertIn("添加设备", OVERVIEW_HTML)

    def test_overview_has_counter_export_and_notifications(self):
        self.assertIn("/api/counters.csv", OVERVIEW_HTML)
        self.assertIn('id="notify"', OVERVIEW_HTML)
        self.assertIn("Notification", OVERVIEW_HTML)


class CliTests(unittest.TestCase):
    def test_web_rejects_json_combination(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["--host", "192.0.2.1", "--web", "--json"])
        self.assertEqual(caught.exception.code, 2)

    def test_web_can_start_without_a_printer(self):
        with mock.patch.object(cli, "run_server") as server:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["--web"]), 0)
        registry = server.call_args.args[0]
        self.assertEqual(registry.hosts(), [])
        self.assertIsNotNone(server.call_args.kwargs["config_workbench"])

    def test_gui_can_start_without_a_printer(self):
        with mock.patch("kyocera_monitor.gui.run_gui") as gui:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["--gui"]), 0)
        registry = gui.call_args.args[0]
        self.assertEqual(registry.hosts(), [])
        self.assertIsNotNone(gui.call_args.kwargs["config_workbench"])

    def test_gui_auto_selects_one_usb_only_printer(self):
        printer = UsbPrinter(
            device="libusb:001:007",
            vendor_id=0x0482,
            product_id=0x0D51,
            manufacturer="KYOCERA",
            product="MA2000w",
            serial="USB123",
        )
        with (
            mock.patch.object(
                cli, "discover_usb_printers", return_value=[]
            ),
            mock.patch.object(
                cli, "discover_libusb_printers", return_value=[printer]
            ),
            mock.patch("kyocera_monitor.gui.run_gui") as gui,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--gui"]), 0)
        registry = gui.call_args.args[0]
        self.assertEqual(registry.hosts(), ["libusb:001:007"])
        self.assertEqual(registry.default, "libusb:001:007")
        self.assertIsNotNone(gui.call_args.kwargs["config_workbench"])

    def test_gui_configuration_uses_pjl_for_automatic_usb_printer(self):
        printer = UsbPrinter(
            device="libusb:001:007",
            vendor_id=0x0482,
            product_id=0x0D51,
            manufacturer="KYOCERA",
            product="MA2000w",
            serial="USB123",
        )
        records = [
            {
                "item_id": obj.item_id,
                "oid": obj.oid,
                "absolute_oid": absolute_config_oid(obj.oid),
                "status": 0,
                "value": 0,
                "display": "0",
            }
            for obj in CONFIG
            if 142 <= obj.item_id <= 147
        ]
        channel = mock.MagicMock()
        channel.__enter__.return_value = channel
        with (
            mock.patch.object(
                cli, "discover_usb_printers", return_value=[]
            ),
            mock.patch.object(
                cli, "discover_libusb_printers", return_value=[printer]
            ),
            mock.patch.object(
                cli, "open_channel", return_value=channel
            ) as open_channel,
            mock.patch.object(
                cli,
                "collect_config",
                return_value=records,
            ) as collect_config,
            mock.patch.object(cli, "collect_config_snmp") as snmp_reader,
            mock.patch("kyocera_monitor.gui.run_gui") as gui,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--gui"]), 0)
            workbench = gui.call_args.kwargs["config_workbench"]
            result = workbench.overview(printer.device, category="wifi")
        self.assertEqual(result["transport"], "pjl")
        self.assertFalse(result["editing"]["available"])
        open_channel.assert_called_once_with(device=printer.device, port=9100)
        self.assertEqual(
            collect_config.call_args.kwargs["item_ids"],
            tuple(range(142, 148)),
        )
        snmp_reader.assert_not_called()

    def test_usb_status_and_configuration_reads_are_serialized(self):
        printer = UsbPrinter(
            device="libusb:001:007",
            vendor_id=0x0482,
            product_id=0x0D51,
            manufacturer="KYOCERA",
            product="MA2000w",
            serial="USB123",
        )
        config_records = [
            {
                "item_id": obj.item_id,
                "oid": obj.oid,
                "absolute_oid": absolute_config_oid(obj.oid),
                "status": 0,
                "value": 0,
                "display": "0",
            }
            for obj in CONFIG
            if 142 <= obj.item_id <= 147
        ]
        channel = mock.MagicMock()
        channel.__enter__.return_value = channel
        status_started = threading.Event()
        release_status = threading.Event()
        config_called = threading.Event()
        failures = []

        def collect_status(*_args, **_kwargs):
            status_started.set()
            release_status.wait(2)
            return b"", snapshot()

        def collect_configuration(*_args, **_kwargs):
            config_called.set()
            return config_records

        def run(target):
            try:
                target()
            except Exception as exc:
                failures.append(exc)

        with (
            mock.patch.object(
                cli, "discover_usb_printers", return_value=[]
            ),
            mock.patch.object(
                cli, "discover_libusb_printers", return_value=[printer]
            ),
            mock.patch.object(
                cli, "collect", side_effect=collect_status
            ),
            mock.patch.object(cli, "open_channel", return_value=channel),
            mock.patch.object(
                cli,
                "collect_config",
                side_effect=collect_configuration,
            ),
            mock.patch("kyocera_monitor.gui.run_gui") as gui,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--gui"]), 0)
            registry = gui.call_args.args[0]
            workbench = gui.call_args.kwargs["config_workbench"]
            status_thread = threading.Thread(
                target=run,
                args=(lambda: registry.read(printer.device),),
            )
            config_thread = threading.Thread(
                target=run,
                args=(
                    lambda: workbench.overview(
                        printer.device,
                        category="wifi",
                    ),
                ),
            )
            status_thread.start()
            self.assertTrue(status_started.wait(1))
            config_thread.start()
            time.sleep(0.05)
            self.assertFalse(config_called.is_set())
            release_status.set()
            status_thread.join(2)
            config_thread.join(2)
        self.assertFalse(status_thread.is_alive())
        self.assertFalse(config_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertTrue(config_called.is_set())

    def test_gui_reports_missing_gtk(self):
        from kyocera_monitor.gui import GuiUnavailable

        with mock.patch(
            "kyocera_monitor.gui.run_gui", side_effect=GuiUnavailable("no gtk")
        ):
            with redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(cli.main(["--gui"]), 2)
        self.assertIn("no gtk", stderr.getvalue())

    def test_gui_requires_a_graphical_session(self):
        from kyocera_monitor.gui import GuiUnavailable, _load_gtk

        with mock.patch.dict(
            os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}
        ):
            with self.assertRaises(GuiUnavailable):
                _load_gtk()

    def test_scan_cli_dispatches_integrated_service(self):
        artifact = ScanArtifact(
            filename="scan.png",
            media_type="image/png",
            kind="png",
            width=2,
            height=1,
            data=b"png",
        )
        result = ScanResult(
            device="192.0.2.1",
            endpoint="http://192.0.2.1:9090/scan",
            operation_id="17",
            pages=1,
            requested_device_format="RAW",
            effective_device_format="RAW",
            outputs=(artifact,),
            close_result="SUCCESS",
            close_error=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "scan.png"
            with mock.patch.object(
                cli, "scan_device", return_value=result
            ) as run, redirect_stderr(io.StringIO()):
                exit_code = cli.main(
                    [
                        "--host",
                        "192.0.2.1",
                        "--scan",
                        "--scan-output",
                        str(output),
                        "--scan-color",
                        "GRAYSCALE",
                    ]
                )
            options = run.call_args.args[1]
            self.assertEqual(exit_code, 0)
            self.assertEqual(options.color, "GRAYSCALE")
            self.assertEqual(output.read_bytes(), b"png")


class ScanApiTests(unittest.TestCase):
    def setUp(self):
        artifact = ScanArtifact(
            filename="scan.png",
            media_type="image/png",
            kind="png",
            width=2,
            height=1,
            data=b"\x89PNG\r\n\x1a\nfake",
        )

        def runner(device, options, progress):
            progress("preflight", "checking")
            progress("complete", "done")
            return ScanResult(
                device=device,
                endpoint=f"http://{device}:9090/scan",
                operation_id="17",
                pages=1,
                requested_device_format="RAW",
                effective_device_format="RAW",
                outputs=(artifact,),
                close_result="SUCCESS",
                close_error=None,
            )

        registry = DeviceRegistry(
            lambda key: snapshot(), "192.0.2.1", min_interval=0
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings_path = Path(self.tmp.name) / "settings.json"
        self.scan_directory = Path(self.tmp.name) / "scans"
        self.settings = SettingsStore(self.settings_path)
        self.manager = ScanJobManager(runner)
        self.handler = make_handler(
            registry,
            scan_manager=self.manager,
            settings_store=self.settings,
        )

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = self.handler.__new__(self.handler)
        request.path = path
        request.headers = {
            "Content-Length": str(len(body or b"")),
            "Content-Type": "application/json",
        }
        request.rfile = io.BytesIO(body or b"")
        request.wfile = io.BytesIO()
        request._status = None
        request._headers = {}

        def send_response(status):
            request._status = status

        def send_header(name, value):
            request._headers[name] = value

        request.send_response = send_response
        request.send_header = send_header
        request.end_headers = lambda: None
        request.log_message = lambda *_args: None
        getattr(request, f"do_{method}")()
        return request._status, request._headers, request.wfile.getvalue()

    def test_scan_job_can_be_polled_and_downloaded(self):
        status, _, body = self.request(
            "POST",
            "/api/scans",
            {
                "host": "192.0.2.1",
                "color": "GRAYSCALE",
                "output_format": "png",
            },
        )
        self.assertEqual(status, 202)
        job = json.loads(body)
        job_id = job["job_id"]
        self.manager.wait(job_id)
        status, _, body = self.request("GET", f"/api/scans/{job_id}")
        self.assertEqual(status, 200)
        job = json.loads(body)
        self.assertEqual(job["state"], "succeeded")
        self.assertEqual(job["result"]["pages"], 1)
        self.assertEqual(
            job["result"]["outputs"][0]["download_url"],
            f"/api/scans/{job_id}/files/0",
        )

        status, headers, data = self.request(
            "GET", f"/api/scans/{job_id}/files/0"
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertIn('filename="scan.png"', headers["Content-Disposition"])
        self.assertIn("filename*=UTF-8''scan.png", headers["Content-Disposition"])
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_invalid_scan_options_return_json_400(self):
        status, _, body = self.request(
            "POST",
            "/api/scans",
            {"host": "192.0.2.1", "output_format": "webp"},
        )
        self.assertEqual(status, 400)
        self.assertIn("unsupported local output format", json.loads(body)["error"])

    def test_settings_api_round_trip(self):
        status, _, body = self.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        initial = json.loads(body)
        initial["scan_directory"] = str(self.scan_directory)
        initial["presets"] = [
            {
                "id": "quick-pdf",
                "name": "快速 PDF",
                "color": "GRAYSCALE",
                "resolution": None,
                "original_image": None,
                "max_pages": 1,
                "output_format": "pdf",
                "push_scan_slot": None,
            }
        ]
        status, _, body = self.request("POST", "/api/settings", initial)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["presets"][0]["id"], "quick-pdf")
        status, _, body = self.request("GET", "/api/settings")
        self.assertEqual(json.loads(body), initial)

    def test_scan_preset_and_save_folder_are_applied(self):
        self.settings.save(
            {
                "version": 1,
                "scan_directory": str(self.scan_directory),
                "presets": [
                    {
                        "id": "gray-pdf",
                        "name": "灰度 PDF",
                        "color": "GRAYSCALE",
                        "resolution": "RESOLUTION_300X300",
                        "original_image": None,
                        "max_pages": 2,
                        "output_format": "pdf",
                    }
                ],
            }
        )
        status, _, body = self.request(
            "POST",
            "/api/scans",
            {
                "host": "192.0.2.1",
                "preset_id": "gray-pdf",
                "save_to_folder": True,
            },
        )
        self.assertEqual(status, 202)
        job_id = json.loads(body)["job_id"]
        self.manager.wait(job_id)
        status, _, body = self.request("GET", f"/api/scans/{job_id}")
        job = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(job["state"], "succeeded")
        self.assertEqual(job["output_format"], "pdf")
        self.assertEqual(len(job["saved_paths"]), 1)
        saved = Path(job["saved_paths"][0])
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.parent, self.scan_directory)
        self.assertEqual(saved.read_bytes(), b"\x89PNG\r\n\x1a\nfake")

    def test_counter_csv_is_stable_and_downloadable(self):
        status, headers, body = self.request("GET", "/api/counters.csv")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/csv; charset=utf-8")
        text = body.decode("utf-8-sig")
        self.assertIn("device,model,serial", text)
        self.assertIn("192.0.2.1,MA2000w,REDACTED", text)


class PrinterPersistenceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = SettingsStore(Path(self.tmp.name) / "settings.json")

    @staticmethod
    def request(handler, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = handler.__new__(handler)
        request.path = path
        request.headers = {
            "Content-Length": str(len(body or b"")),
            "Content-Type": "application/json",
        }
        request.rfile = io.BytesIO(body or b"")
        request.wfile = io.BytesIO()
        request._status = None
        request._headers = {}

        def send_response(status):
            request._status = status

        def send_header(name, value):
            request._headers[name] = value

        request.send_response = send_response
        request.send_header = send_header
        request.end_headers = lambda: None
        request.log_message = lambda *_args: None
        getattr(request, f"do_{method}")()
        return request._status, request._headers, request.wfile.getvalue()

    def test_manual_device_is_saved_and_restored_after_restart(self):
        registry = DeviceRegistry(lambda key: snapshot(), None, min_interval=0)
        handler = make_handler(registry, settings_store=self.settings)
        status, _, body = self.request(
            handler,
            "POST",
            "/api/devices",
            {"host": "192.168.000.220"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(body)["device"],
            "192.168.0.220",
        )
        self.assertEqual(
            self.settings.load()["saved_printers"],
            ["192.168.0.220"],
        )

        restarted = DeviceRegistry(
            lambda key: snapshot(), None, min_interval=0
        )
        make_handler(restarted, settings_store=self.settings)
        self.assertEqual(restarted.hosts(), ["192.168.0.220"])

    def test_discovery_saves_all_found_devices(self):
        printers = [
            DiscoveredPrinter(address="192.168.0.220", model="MA2000w"),
            DiscoveredPrinter(address="192.168.0.221", model="MA2000w"),
        ]
        registry = DeviceRegistry(lambda key: snapshot(), None, min_interval=0)
        handler = make_handler(
            registry,
            discover_fn=lambda: printers,
            settings_store=self.settings,
        )
        status, _, body = self.request(handler, "GET", "/api/discover")
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)["warning"])
        self.assertEqual(
            self.settings.load()["saved_printers"],
            ["192.168.0.220", "192.168.0.221"],
        )

    def test_preferences_save_without_printer_list_preserves_saved_devices(self):
        self.settings.update_saved_printers(["192.168.0.220"])
        registry = DeviceRegistry(lambda key: snapshot(), None, min_interval=0)
        handler = make_handler(registry, settings_store=self.settings)
        status, _, _ = self.request(
            handler,
            "POST",
            "/api/settings",
            {
                "version": 1,
                "scan_directory": str(Path(self.tmp.name) / "scans"),
                "presets": [],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.settings.load()["saved_printers"],
            ["192.168.0.220"],
        )


class ConfigApiTests(unittest.TestCase):
    def setUp(self):
        registry = DeviceRegistry(
            lambda key: snapshot(), "192.0.2.1", min_interval=0
        )
        self.workbench = mock.Mock()
        self.handler = make_handler(
            registry,
            config_workbench=self.workbench,
        )

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = self.handler.__new__(self.handler)
        request.path = path
        request.headers = {
            "Content-Length": str(len(body or b"")),
            "Content-Type": "application/json",
        }
        request.rfile = io.BytesIO(body or b"")
        request.wfile = io.BytesIO()
        request._status = None
        request._headers = {}

        def send_response(status):
            request._status = status

        def send_header(name, value):
            request._headers[name] = value

        request.send_response = send_response
        request.send_header = send_header
        request.end_headers = lambda: None
        request.log_message = lambda *_args: None
        getattr(request, f"do_{method}")()
        return request._status, request._headers, request.wfile.getvalue()

    def test_config_read_and_baseline_info_are_dispatched(self):
        self.workbench.overview.return_value = {
            "host": "192.0.2.1",
            "read": 96,
            "total": 147,
            "status_objects": [],
            "objects": [],
        }
        self.workbench.baseline_info.return_value = {"available": False}
        status, _, body = self.request(
            "GET", "/api/config?host=192.0.2.1"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["read"], 96)
        self.workbench.overview.assert_called_once_with(
            "192.0.2.1",
            category="general",
        )

        status, _, body = self.request(
            "GET", "/api/config/baseline?host=192.0.2.1"
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["baseline"]["available"])

    def test_config_categories_and_scoped_read(self):
        self.workbench.category_catalog.return_value = [
            {
                "key": "wifi",
                "label": "Wi-Fi",
                "description": "wifi",
                "item_count": 6,
                "editable_count": 0,
            }
        ]
        status, _, body = self.request(
            "GET",
            "/api/config/categories?host=192.0.2.1",
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["total"], 6)

        self.workbench.overview.return_value = {
            "host": "192.0.2.1",
            "read": 5,
            "total": 6,
            "status_objects": [],
            "objects": [],
        }
        status, _, body = self.request(
            "GET",
            "/api/config?host=192.0.2.1&category=wifi",
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["total"], 6)
        self.workbench.overview.assert_called_once_with(
            "192.0.2.1",
            category="wifi",
        )

    def test_config_transport_failure_returns_json_error(self):
        self.workbench.overview.side_effect = ConfigWorkbenchError(
            "TimeoutError: device did not answer"
        )
        status, headers, body = self.request(
            "GET",
            "/api/config?host=192.0.2.1&category=general",
        )
        self.assertEqual(status, 502)
        self.assertEqual(
            headers["Content-Type"],
            "application/json; charset=utf-8",
        )
        self.assertIn(
            "device did not answer",
            json.loads(body)["error"],
        )

    def test_unexpected_config_failure_keeps_http_connection_alive(self):
        self.workbench.overview.side_effect = RuntimeError("malformed result")
        status, headers, body = self.request(
            "GET",
            "/api/config?host=192.0.2.1&category=general",
        )
        self.assertEqual(status, 502)
        self.assertEqual(
            headers["Content-Type"],
            "application/json; charset=utf-8",
        )
        self.assertIn("malformed result", json.loads(body)["error"])

    def test_baseline_and_reviewed_write_dispatch(self):
        self.workbench.save_baseline.return_value = {"saved": True}
        status, _, _ = self.request(
            "POST",
            "/api/config/baseline",
            {"host": "192.0.2.1"},
        )
        self.assertEqual(status, 200)
        self.workbench.save_baseline.assert_called_once_with("192.0.2.1")

        status, _, _ = self.request(
            "POST",
            "/api/config/plan",
            {"host": "192.0.2.1", "item_id": 2, "value": "ON"},
        )
        self.assertEqual(status, 404)
        self.workbench.plan.assert_not_called()

        self.workbench.apply_integer.return_value = {
            "status": "applied",
            "item_id": 50,
            "before": 0,
            "requested": 1,
            "observed": 1,
        }
        status, _, _ = self.request(
            "POST",
            "/api/config/apply",
            {
                "host": "192.0.2.1",
                "item_id": 50,
                "value": 1,
                "expected_value": 0,
                "confirm": True,
            },
        )
        self.assertEqual(status, 200)
        self.workbench.apply_integer.assert_called_once_with(
            "192.0.2.1",
            50,
            1,
            0,
        )

    def test_reviewed_write_requires_confirmation(self):
        status, _, body = self.request(
            "POST",
            "/api/config/apply",
            {
                "host": "192.0.2.1",
                "item_id": 50,
                "value": 1,
                "expected_value": 0,
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("confirm=true", json.loads(body)["error"])
        self.workbench.apply_integer.assert_not_called()


class WifiApiTests(unittest.TestCase):
    def setUp(self):
        registry = DeviceRegistry(
            lambda key: snapshot(), "192.0.2.1", min_interval=0
        )
        self.workbench = mock.Mock()
        self.handler = make_handler(registry, wifi_workbench=self.workbench)

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = self.handler.__new__(self.handler)
        request.path = path
        request.headers = {
            "Content-Length": str(len(body or b"")),
            "Content-Type": "application/json",
        }
        request.rfile = io.BytesIO(body or b"")
        request.wfile = io.BytesIO()
        request._status = None
        request._headers = {}

        def send_response(status):
            request._status = status

        def send_header(name, value):
            request._headers[name] = value

        request.send_response = send_response
        request.send_header = send_header
        request.end_headers = lambda: None
        request.log_message = lambda *_args: None
        getattr(request, f"do_{method}")()
        return request._status, request._headers, request.wfile.getvalue()

    def test_wifi_status_and_scan_are_dispatched(self):
        self.workbench.status.return_value = {
            "connected": True,
            "ssid": "Office",
        }
        self.workbench.scan.return_value = [{"ssid": "Office"}]
        status, _, body = self.request(
            "GET", "/api/wifi/status?host=192.0.2.1"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["ssid"], "Office")
        self.workbench.status.assert_called_once_with("192.0.2.1")

        status, _, body = self.request(
            "GET", "/api/wifi/scan?host=192.0.2.1"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)[0]["ssid"], "Office")
        self.workbench.scan.assert_called_once_with("192.0.2.1")

    def test_wifi_connect_requires_confirmation_and_dispatches(self):
        status, _, body = self.request(
            "POST",
            "/api/wifi/connect",
            {
                "host": "192.0.2.1",
                "ssid": "Office",
                "security": 4,
                "password": "secret",
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("confirm=true", json.loads(body)["error"])
        self.workbench.connect.assert_not_called()

        self.workbench.connect.return_value = {
            "connected": True,
            "ssid": "Office",
            "security_name": "WPA2 PSK (AES)",
        }
        status, _, body = self.request(
            "POST",
            "/api/wifi/connect",
            {
                "host": "192.0.2.1",
                "ssid": "Office",
                "security": 4,
                "password": "secret",
                "bssid": "AA:BB:CC:DD:EE:FF",
                "confirm": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["connected"])
        self.workbench.connect.assert_called_once_with(
            "192.0.2.1",
            ssid="Office",
            security=4,
            password="secret",
            bssid="AA:BB:CC:DD:EE:FF",
            wep_index=0,
        )


if __name__ == "__main__":
    unittest.main()
