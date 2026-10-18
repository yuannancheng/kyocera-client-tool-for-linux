import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "tools"))

import clienttool_oid_semantics as semantics  # noqa: E402


class ClientToolOidSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = semantics.load_semantics()
        cls.inventory = semantics.load_inventory()
        cls.by_oid = {row["oid"]: row for row in cls.rows}

    def test_table_shape_and_groups(self):
        self.assertEqual(len(self.rows), 62)
        self.assertEqual(len(self.by_oid), 62)
        self.assertEqual(
            sum(1 for row in self.rows if row["group"] == "Print Box"), 7
        )
        self.assertEqual(
            sum(1 for row in self.rows if row["group"] == "Push Scan"), 6
        )
        self.assertEqual(
            sum(1 for row in self.rows if row["group"] == "Preset"), 5
        )

    def test_semantics_only_cover_formerly_unnamed_oids(self):
        inventory = {row["oid"]: row for row in self.inventory}
        for oid in self.by_oid:
            self.assertIn(oid, inventory)
            self.assertEqual(inventory[oid]["symbols"], "")
        # Prefix symbols are inherited heuristics; four Wi-Fi columns carry a
        # misleading vendor prefix and are intentionally overridden.
        overrides = [
            oid
            for oid in self.by_oid
            if inventory[oid]["prefix_symbols"]
        ]
        self.assertEqual(len(overrides), 4)

    def test_interface_and_address_type_enums(self):
        for oid in (
            "1.3.6.1.4.1.1347.1001.3.1.1.0",
            "1.3.6.1.4.1.1347.1001.4.1.1.0",
        ):
            self.assertIn("0=USB;1=NETWORK", self.by_oid[oid]["values"])
        for oid in (
            "1.3.6.1.4.1.1347.1001.3.1.7.0",
            "1.3.6.1.4.1.1347.1001.4.1.6.0",
        ):
            self.assertEqual(
                self.by_oid[oid]["values"],
                "1=IPv4;2=IPv6;3=HostName",
            )

    def test_result_enums(self):
        pbox = self.by_oid["1.3.6.1.4.1.1347.1001.3.1.3.0"]
        self.assertIn("0=ACCEPTED", pbox["values"])
        self.assertIn("3=WRONG PIN", pbox["values"])
        pscn = self.by_oid["1.3.6.1.4.1.1347.1001.4.1.3.0"]
        self.assertEqual(pscn["values"], "0=OK;1=NG")

    def test_ipv6_objects_are_octet_strings(self):
        for oid in (
            "1.3.6.1.4.1.1347.1001.3.1.5.0",
            "1.3.6.1.4.1.1347.1001.4.1.4.0",
        ):
            row = self.by_oid[oid]
            self.assertEqual(row["snmp_type"], "OctetString")
            self.assertIn("16-byte IPv6", row["value_encoding"])

    def test_coverage_accounts_for_all_unnamed_device_oids(self):
        summary = semantics.coverage(self.inventory, self.rows)
        self.assertEqual(summary["inventory_oids"], 827)
        self.assertEqual(summary["library_constants"], 91)
        self.assertEqual(summary["device_oids"], 736)
        self.assertEqual(summary["unnamed"], 59)
        self.assertEqual(summary["covered"], 58)
        self.assertEqual(summary["remaining"], 1)
        self.assertEqual(
            summary["remaining_oids"],
            ["1.3.6.1.4.1.1347.42.27.6.0"],
        )
        self.assertEqual(summary["missing_from_inventory"], [])
        self.assertEqual(summary["conflicting_with_vendor_name"], [])
        self.assertEqual(len(summary["prefix_symbol_overrides"]), 4)

    def test_wifi_and_pac_semantics(self):
        expected = {
            "1.3.6.1.4.1.1347.40.39.1.1.10.1.1": "access_points_total",
            "1.3.6.1.4.1.1347.40.40.1.1.9.1": (
                "set_access_point_pre_shared_key"
            ),
            "1.3.6.1.4.1.1347.40.42.1.1.1.1": "wifi_connection_state",
            "1.3.6.1.4.1.1347.42.26.2.1.0": "ldap_server_name",
            "1.3.6.1.4.1.1347.42.27.7.0": "max_groups",
            "1.3.6.1.4.1.1347.42.5.1.1.13.1": "panel_size_unit",
            "1.3.6.1.4.1.1347.43.10.1.1.8.1.1": "drum_counter",
        }
        for oid, name in expected.items():
            self.assertEqual(self.by_oid[oid]["semantic_name"], name)

    def test_panel_size_and_wifi_state_values(self):
        self.assertIn("3=INCH", self.by_oid[
            "1.3.6.1.4.1.1347.42.5.1.1.13.1"
        ]["values"])
        self.assertEqual(
            self.by_oid["1.3.6.1.4.1.1347.40.42.1.1.1.1"]["values"],
            "3=ON/Connected;4=OFF/Not connected (UI labels)",
        )

    def test_merge_adds_semantic_columns(self):
        merged = semantics.merge_rows(self.inventory, self.rows)
        selected = {
            row["oid"]: row
            for row in merged
            if row["oid"] in self.by_oid
        }
        self.assertEqual(
            selected["1.3.6.1.4.1.1347.1001.3.1.2.0"]["semantic_group"],
            "Print Box",
        )
        self.assertEqual(
            selected["1.3.6.1.4.1.1347.1001.4.1.6.0"]["semantic_type"],
            "Integer",
        )

    def test_preset_reset_targets_and_lock(self):
        expected = {
            "1.3.6.1.4.1.1347.1001.1.1.6.0": (
                "preset_reset_copy",
                "Integer",
            ),
            "1.3.6.1.4.1.1347.1001.1.1.7.0": (
                "preset_reset_scan",
                "Integer",
            ),
            "1.3.6.1.4.1.1347.1001.1.1.8.0": (
                "preset_reset_fax",
                "Integer",
            ),
            "1.3.6.1.4.1.1347.1001.1.1.9.0": (
                "preset_reset_print_box",
                "Integer",
            ),
            "1.3.6.1.4.1.1347.1001.1.1.10.0": (
                "preset_security_lock",
                "OctetString",
            ),
        }
        for oid, (name, snmp_type) in expected.items():
            self.assertEqual(self.by_oid[oid]["semantic_name"], name)
            self.assertEqual(self.by_oid[oid]["snmp_type"], snmp_type)


if __name__ == "__main__":
    unittest.main()
