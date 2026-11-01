import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from kyocera_monitor import cli
from kyocera_monitor.discovery import DiscoveredPrinter
from kyocera_monitor.parser import PrinterSnapshot, Tray
from kyocera_monitor.preferences import SettingsStore
from kyocera_monitor.scan import ScanArtifact, ScanJobManager, ScanResult
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

    def test_device_page_shows_counters_and_settings(self):
        for element_id in ("lifetime", "scan", "drum", "settings"):
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

    def test_device_page_has_guarded_configuration_workflow(self):
        for element_id in (
            "config-read",
            "config-baseline-save",
            "config-baseline-compare",
            "config-status-grid",
            "config-objects",
            "config-write-item",
            "config-plan",
            "config-apply",
            "config-authorize",
        ):
            self.assertIn(f'id="{element_id}"', DEVICE_HTML)
        self.assertIn("/api/config/plan", DEVICE_HTML)
        self.assertIn("/api/config/apply", DEVICE_HTML)
        self.assertIn("OFF → ON → OFF", DEVICE_HTML)

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
            "candidates": [],
        }
        self.workbench.baseline_info.return_value = {"available": False}
        status, _, body = self.request(
            "GET", "/api/config?host=192.0.2.1"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["read"], 96)
        self.workbench.overview.assert_called_once_with("192.0.2.1")

        status, _, body = self.request(
            "GET", "/api/config/baseline?host=192.0.2.1"
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["baseline"]["available"])

    def test_baseline_plan_and_apply_dispatch(self):
        self.workbench.save_baseline.return_value = {"saved": True}
        status, _, _ = self.request(
            "POST",
            "/api/config/baseline",
            {"host": "192.0.2.1"},
        )
        self.assertEqual(status, 200)
        self.workbench.save_baseline.assert_called_once_with("192.0.2.1")

        self.workbench.plan.return_value = {"plan": {"ok": True}}
        status, _, _ = self.request(
            "POST",
            "/api/config/plan",
            {"host": "192.0.2.1", "item_id": 2, "value": "ON"},
        )
        self.assertEqual(status, 200)
        self.workbench.plan.assert_called_once_with("192.0.2.1", 2, "ON")

        self.workbench.apply.return_value = {"execution": {"status": "success"}}
        status, _, _ = self.request(
            "POST",
            "/api/config/apply",
            {
                "host": "192.0.2.1",
                "item_id": 2,
                "value": "ON",
                "confirmation_token": "sha256:" + "a" * 64,
            },
        )
        self.assertEqual(status, 200)
        self.workbench.apply.assert_called_once_with(
            "192.0.2.1", 2, "ON", "sha256:" + "a" * 64
        )

    def test_apply_without_confirmation_never_reaches_workbench(self):
        status, _, body = self.request(
            "POST",
            "/api/config/apply",
            {"host": "192.0.2.1", "item_id": 2, "value": "ON"},
        )
        self.assertEqual(status, 400)
        self.assertIn("confirmation_token", json.loads(body)["error"])
        self.workbench.apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
