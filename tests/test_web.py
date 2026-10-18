import io
import os
import unittest
from contextlib import redirect_stderr
from unittest import mock

from kyocera_monitor import cli
from kyocera_monitor.parser import PrinterSnapshot, Tray
from kyocera_monitor.web import (
    DEVICE_HTML,
    OVERVIEW_HTML,
    DeviceRegistry,
    SnapshotCache,
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

    def test_pages_are_self_contained(self):
        for page in (OVERVIEW_HTML, DEVICE_HTML):
            self.assertNotIn("http://", page)
            self.assertNotIn("https://", page)

    def test_overview_has_manual_device_form(self):
        self.assertIn('id="add"', OVERVIEW_HTML)
        self.assertIn('id="host"', OVERVIEW_HTML)
        self.assertIn('method: "POST"', OVERVIEW_HTML)
        self.assertIn("添加设备", OVERVIEW_HTML)


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

    def test_gui_can_start_without_a_printer(self):
        with mock.patch("kyocera_monitor.gui.run_gui") as gui:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["--gui"]), 0)
        registry = gui.call_args.args[0]
        self.assertEqual(registry.hosts(), [])

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


if __name__ == "__main__":
    unittest.main()
