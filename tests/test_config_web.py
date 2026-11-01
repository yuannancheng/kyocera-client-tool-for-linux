import copy
import tempfile
import unittest
from pathlib import Path

from kyocera_monitor.config import CONFIG, absolute_config_oid
from kyocera_monitor.config_web import ConfigWorkbench


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

    def test_web_workbench_is_read_only(self):
        workbench = ConfigWorkbench(
            lambda _host: records(),
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        self.assertFalse(hasattr(workbench, "plan"))
        self.assertFalse(hasattr(workbench, "apply"))


if __name__ == "__main__":
    unittest.main()
