import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kyocera_monitor.config import CONFIG, absolute_config_oid
from kyocera_monitor.config_web import (
    CONFIG_SECTIONS,
    ConfigCategoryError,
    ConfigWorkbench,
    ConfigWorkbenchError,
)


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
    def test_categories_match_official_pages_and_cover_every_item_once(self):
        item_ids = [
            item_id
            for section in CONFIG_SECTIONS
            for item_id in section.item_ids
        ]
        self.assertEqual(len(item_ids), 147)
        self.assertEqual(sorted(item_ids), list(range(1, 148)))
        self.assertEqual(
            [section.key for section in CONFIG_SECTIONS],
            [
                "general",
                "paper",
                "communication",
                "snmp_traps",
                "panel",
                "fax",
                "wifi",
            ],
        )
        workbench = ConfigWorkbench(
            lambda _host: records(),
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        catalog = {
            category["key"]: category
            for category in workbench.category_catalog()
        }
        self.assertEqual(
            sum(category["editable_count"] for category in catalog.values()),
            27,
        )
        self.assertEqual(catalog["general"]["editable_count"], 8)
        self.assertEqual(catalog["paper"]["editable_count"], 17)
        self.assertEqual(catalog["wifi"]["editor"], "dedicated")
        self.assertEqual(catalog["communication"]["editor"], "read_only")

    def test_overview_is_scoped_and_redacts_sensitive_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbench = ConfigWorkbench(
                lambda _host: records(),
                baseline_directory=Path(tmp),
            )
            general = workbench.overview("printer", category="general")
            wifi = workbench.overview("printer", category="wifi")
        self.assertEqual(general["read"], 15)
        self.assertEqual(general["total"], 15)
        self.assertEqual(general["full_total"], 147)
        self.assertIn(
            50,
            {item["item_id"] for item in general["editing"]["items"]},
        )
        self.assertEqual(wifi["read"], 6)
        by_id = {item["item_id"]: item for item in wifi["status_objects"]}
        self.assertEqual(by_id[142]["display"], "Connected")
        self.assertEqual(by_id[146]["display"], "-70 dBm")
        self.assertEqual(by_id[144]["display"], "<redacted>")
        self.assertTrue(by_id[144]["sensitive"])
        all_by_id = {item["item_id"]: item for item in wifi["objects"]}
        self.assertEqual(all_by_id[144]["display"], "<redacted>")
        general_by_id = {
            item["item_id"]: item for item in general["objects"]
        }
        self.assertNotIn("write_policy", general_by_id[50])
        self.assertNotIn("candidates", general)
        self.assertNotIn("write_execution_available", general)
        self.assertFalse(general["editing"]["available"])

    def test_unknown_category_fails_closed(self):
        workbench = ConfigWorkbench(
            lambda _host: records(),
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        with self.assertRaises(ConfigCategoryError):
            workbench.overview("printer", category="not-a-page")

    def test_scoped_transport_errors_become_workbench_errors(self):
        def timed_out(_host, _item_ids):
            raise TimeoutError("device did not answer")

        workbench = ConfigWorkbench(
            mock.Mock(side_effect=AssertionError("full read must not be used")),
            scoped_reader=timed_out,
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        with self.assertRaisesRegex(
            ConfigWorkbenchError,
            "TimeoutError: device did not answer",
        ):
            workbench.overview("printer", category="general")

    def test_transport_and_write_availability_can_depend_on_target(self):
        workbench = ConfigWorkbench(
            lambda _host: records(),
            scoped_reader=lambda _host, item_ids: [
                record for record in records()
                if record["item_id"] in set(item_ids)
            ],
            writer=mock.Mock(),
            writer_available=lambda host: not host.startswith("libusb:"),
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
            transport=lambda host: (
                "pjl" if host.startswith("libusb:") else "snmp"
            ),
        )
        usb = workbench.overview("libusb:001:007", category="wifi")
        network = workbench.overview("printer", category="wifi")
        self.assertEqual(usb["transport"], "pjl")
        self.assertFalse(usb["editing"]["available"])
        self.assertEqual(network["transport"], "snmp")
        self.assertTrue(network["editing"]["available"])

    def test_reviewed_editors_replace_duplicate_status_cards_when_writable(self):
        workbench = ConfigWorkbench(
            lambda _host: records(),
            scoped_reader=lambda _host, item_ids: [
                record for record in records()
                if record["item_id"] in set(item_ids)
            ],
            writer=mock.Mock(),
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        general = workbench.overview("printer", category="general")
        paper = workbench.overview("printer", category="paper")
        self.assertEqual(general["status_objects"], [])
        self.assertEqual(
            {item["item_id"] for item in general["editing"]["items"]},
            {1, 2, 3, 10, 49, 50, 51, 52},
        )
        self.assertEqual(
            {item["item_id"] for item in paper["editing"]["items"]},
            {
                11,
                12,
                14,
                15,
                17,
                18,
                19,
                20,
                24,
                25,
                26,
                27,
                28,
                29,
                30,
                31,
                32,
            },
        )

    def test_unreadable_items_are_hidden_and_media_values_are_friendly(self):
        current = records()
        by_id = {record["item_id"]: record for record in current}
        by_id[6]["value"] = 9
        by_id[9]["value"] = 1
        by_id[11]["value"] = 11
        for item_id in (12, 13, 22):
            by_id[item_id]["status"] = 2
            by_id[item_id]["value"] = None
            by_id[item_id]["display"] = None
        workbench = ConfigWorkbench(
            lambda _host: current,
            writer=mock.Mock(),
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        paper = workbench.overview("printer", category="paper")
        visible = {item["item_id"]: item for item in paper["objects"]}
        self.assertEqual(paper["hidden_count"], 3)
        self.assertNotIn(12, visible)
        self.assertNotIn(13, visible)
        self.assertNotIn(22, visible)
        self.assertEqual(visible[6]["display"], "A4")
        self.assertEqual(visible[9]["display"], "普通纸")
        self.assertEqual(visible[11]["display"], "普通 1")
        self.assertNotIn(
            12,
            {item["item_id"] for item in paper["editing"]["items"]},
        )
        read_only = {
            item["item_id"]: item for item in paper["read_only_objects"]
        }
        self.assertEqual(read_only[6]["label"], "Default paper size")
        self.assertEqual(read_only[9]["label"], "Default media type")

    def test_pjl_records_without_absolute_oid_still_render(self):
        pjl_records = []
        for record in records():
            record = copy.deepcopy(record)
            record.pop("absolute_oid", None)
            pjl_records.append(record)
        workbench = ConfigWorkbench(
            lambda _host: pjl_records,
            scoped_reader=lambda _host, item_ids: [
                record for record in pjl_records
                if record["item_id"] in set(item_ids)
            ],
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
            transport="pjl",
        )
        result = workbench.overview(
            "libusb:001:007",
            category="wifi",
        )
        by_id = {item["item_id"]: item for item in result["objects"]}
        self.assertEqual(
            by_id[142]["absolute_oid"],
            absolute_config_oid(
                next(obj.oid for obj in CONFIG if obj.item_id == 142)
            ),
        )

    def test_scoped_reader_limits_page_and_write_readback_to_requested_items(self):
        current = {"value": records(quiet_mode=0)}
        calls = []

        def scoped_reader(_host, item_ids):
            calls.append(item_ids)
            selected = set(item_ids)
            return [
                copy.deepcopy(record)
                for record in current["value"]
                if record["item_id"] in selected
            ]

        def writer(_host, _oid, value):
            current["value"] = records(quiet_mode=value)

        workbench = ConfigWorkbench(
            mock.Mock(side_effect=AssertionError("full read must not be used")),
            scoped_reader=scoped_reader,
            writer=writer,
            baseline_directory=Path("/tmp/unused-kyocera-baseline"),
        )
        page = workbench.overview("printer", category="wifi")
        self.assertEqual(page["total"], 6)
        result = workbench.apply_integer("printer", 50, 1, 0)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(tuple(range(142, 148)), calls[0])
        self.assertEqual([(50,), (50,)], calls[1:])

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
