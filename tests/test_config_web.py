import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kyocera_monitor.config import CONFIG, absolute_config_oid
from kyocera_monitor.config_web import ConfigWorkbench, ConfigWorkbenchError


def records(*, quiet_mode=0, connected=True, wifi_changes=False):
    values = []
    for obj in CONFIG:
        value = 0
        display = "0"
        if obj.item_id == 2:
            value = 0
            display = "OFF"
        elif obj.item_id == 50:
            value = quiet_mode
            display = "ON" if quiet_mode else "OFF"
        elif obj.item_id == 84:
            value = 1
            display = "ON"
        elif obj.item_id == 142:
            value = 3 if connected else 4
            display = "Connected" if connected else "Not connected"
        elif obj.item_id == 143:
            value = 1
            display = "ON"
        elif obj.item_id == 144:
            value = "Office Wi-Fi"
            display = "Office Wi-Fi"
        elif obj.item_id == 145:
            value = 2
            display = "WPA2/WPA PSK (AES)"
        elif obj.item_id == 146:
            value = -70 if not wifi_changes else -75
            display = f"{value} dBm"
        elif obj.item_id == 147:
            value = 6 if not wifi_changes else 11
            display = str(value)
        values.append(
            {
                "item_id": obj.item_id,
                "oid": obj.oid,
                "absolute_oid": absolute_config_oid(obj.oid),
                "type_code": obj.type_code,
                "status": 0,
                "value": value,
                "display": display,
            }
        )
    return values


class ConfigWorkbenchTests(unittest.TestCase):
    def test_overview_redacts_sensitive_values_and_exposes_wifi_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbench = ConfigWorkbench(
                lambda _host: records(),
                baseline_directory=Path(tmp),
            )
            result = workbench.overview("printer")
        self.assertEqual(result["read"], 147)
        by_id = {item["item_id"]: item for item in result["status_objects"]}
        self.assertEqual(by_id[142]["display"], "Connected")
        self.assertEqual(by_id[146]["display"], "-70 dBm")
        self.assertEqual(by_id[144]["display"], "<redacted>")
        self.assertTrue(by_id[144]["sensitive"])
        all_by_id = {item["item_id"]: item for item in result["objects"]}
        self.assertEqual(all_by_id[144]["display"], "<redacted>")
        self.assertNotIn("write_policy", all_by_id[50])
        self.assertNotIn("candidates", result)
        self.assertNotIn("write_execution_available", result)
        self.assertNotIn("warning", result)
        self.assertFalse(result["editing"]["available"])
        self.assertIn(
            50,
            {item["item_id"] for item in result["editing"]["items"]},
        )

    def test_baseline_compare_and_private_storage(self):
        current = {"value": records()}

        def reader(_host):
            return copy.deepcopy(current["value"])

        with tempfile.TemporaryDirectory() as tmp:
            workbench = ConfigWorkbench(
                reader,
                baseline_directory=Path(tmp),
            )
            saved = workbench.save_baseline("printer")
            self.assertTrue(saved["saved"])
            path = Path(saved["path"])
            self.assertEqual(path.parent, Path(tmp))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            current["value"] = records(quiet_mode=1, wifi_changes=True)
            comparison = workbench.compare_baseline("printer")
        self.assertEqual(comparison["comparison"]["changed"], 1)
        self.assertEqual(comparison["comparison"]["volatile_changed"], 2)
        self.assertEqual(comparison["comparison"]["read_status_changed"], 0)

    def test_web_workbench_has_no_experimental_plan_or_apply_methods(self):
        workbench = ConfigWorkbench(
            lambda _host: records(),
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        self.assertFalse(hasattr(workbench, "plan"))
        self.assertFalse(hasattr(workbench, "apply"))

    def test_reviewed_integer_write_reads_back(self):
        current = {"value": records(quiet_mode=0)}

        def reader(_host):
            return copy.deepcopy(current["value"])

        def writer(host, oid, value):
            self.assertEqual(host, "printer")
            self.assertEqual(
                oid,
                "1.3.6.1.4.1.1347.1001.2.1.1.1.14.1",
            )
            current["value"] = records(quiet_mode=value)
            return mock.Mock()

        workbench = ConfigWorkbench(
            reader,
            writer=writer,
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        result = workbench.apply_integer("printer", 50, 1, 0)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["before"], 0)
        self.assertEqual(result["requested"], 1)
        self.assertEqual(result["observed"], 1)

    def test_write_rejects_stale_page_state_without_calling_writer(self):
        writer = mock.Mock()
        workbench = ConfigWorkbench(
            lambda _host: records(quiet_mode=1),
            writer=writer,
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        with self.assertRaisesRegex(ConfigWorkbenchError, "configuration changed"):
            workbench.apply_integer("printer", 50, 0, 0)
        writer.assert_not_called()

    def test_failed_readback_attempts_restore(self):
        calls = []

        def writer(_host, _oid, value):
            calls.append(value)

        workbench = ConfigWorkbench(
            lambda _host: records(quiet_mode=0),
            writer=writer,
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        with self.assertRaisesRegex(
            ConfigWorkbenchError,
            "did not read back",
        ):
            workbench.apply_integer(
                "printer",
                50,
                1,
                0,
                readback_timeout=0,
            )
        self.assertEqual(calls, [1, 0])


if __name__ == "__main__":
    unittest.main()
