import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"

sys.path.insert(0, str(ROOT / "tools"))

import clienttool_all_oids  # noqa: E402


class ClientToolAllOidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DATA / "clienttool-all-oids.tsv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle, delimiter="\t"))
        cls.by_oid = {row["oid"]: row for row in cls.rows}

    def test_extract_ascii_utf16_and_leading_dot(self):
        ascii_oid = b"1.3.6.1.4.1.1347.1"
        utf16_oid = "1.3.6.1.4.1.1347.2".encode("utf-16le")
        data = b"x " + ascii_oid + b" y .1.3.6.1.4.1.1347.3 " + utf16_oid
        found = {
            oid
            for oid, _, _ in clienttool_all_oids.extract_oids(data)
        }
        self.assertEqual(
            found,
            {
                "1.3.6.1.4.1.1347.1",
                "1.3.6.1.4.1.1347.2",
                "1.3.6.1.4.1.1347.3",
            },
        )

    def test_utf16_leading_dot_with_nul_terminators(self):
        # Regression: the old UTF-16 boundary assertion rejected a leading
        # dot preceded by a NUL character and a string followed by a
        # terminator, hiding standalone ".1.3.6.1..." heap literals.
        oid = "1.3.6.1.4.1.1347.42.26.1.0"
        data = b"\x00\x00" + ("." + oid).encode("utf-16le") + b"\x00\x00"
        found = {
            value for value, _, _ in clienttool_all_oids.extract_oids(data)
        }
        self.assertEqual(found, {oid})

    def test_short_and_ip_like_numbers_are_ignored(self):
        data = b"1.3.6.1 1.2.3.4 1.3.6.1.2.1"
        found = [
            oid for oid, _, _ in clienttool_all_oids.extract_oids(data)
        ]
        self.assertEqual(found, ["1.3.6.1.2.1"])

    def test_inventory_shape(self):
        self.assertEqual(len(self.rows), 827)
        self.assertEqual(len(self.by_oid), 827)
        self.assertEqual(
            sum(1 for row in self.rows if row["semantic_name"]), 62
        )
        sources = "\n".join(row["sources"] for row in self.rows)
        self.assertIn("KMSTMNET.exe", sources)
        self.assertIn("FAX/KMSNMP4.INI", sources)

    def test_curated_semantics_cover_print_box_and_push_scan(self):
        expected = {
            "1.3.6.1.4.1.1347.1001.3.1.1.0": "print_box_interface",
            "1.3.6.1.4.1.1347.1001.3.1.2.0": "print_box_ipv4_address",
            "1.3.6.1.4.1.1347.1001.3.1.3.0": "print_box_result",
            "1.3.6.1.4.1.1347.1001.3.1.4.0": "print_box_pin_code",
            "1.3.6.1.4.1.1347.1001.3.1.5.0": "print_box_ipv6_address",
            "1.3.6.1.4.1.1347.1001.3.1.6.0": "print_box_host_name",
            "1.3.6.1.4.1.1347.1001.3.1.7.0": "print_box_address_type",
            "1.3.6.1.4.1.1347.1001.4.1.1.0": "push_scan_interface",
            "1.3.6.1.4.1.1347.1001.4.1.2.0": "push_scan_ipv4_address",
            "1.3.6.1.4.1.1347.1001.4.1.3.0": "push_scan_result",
            "1.3.6.1.4.1.1347.1001.4.1.4.0": "push_scan_ipv6_address",
            "1.3.6.1.4.1.1347.1001.4.1.5.0": "push_scan_host_name",
            "1.3.6.1.4.1.1347.1001.4.1.6.0": "push_scan_address_type",
        }
        for oid, semantic_name in expected.items():
            row = self.by_oid[oid]
            self.assertEqual(row["semantic_name"], semantic_name)
            self.assertEqual(row["symbols"], "")

    def test_semantics_reduce_unresolved_device_oids_to_one(self):
        unresolved = [
            row
            for row in self.rows
            if row["oid_role"] != "library-constant"
            if not row["symbols"]
            and not row["prefix_symbols"]
            and not row["semantic_name"]
        ]
        self.assertEqual(
            [row["oid"] for row in unresolved],
            ["1.3.6.1.4.1.1347.42.27.6.0"],
        )

    def test_third_party_crypto_arcs_are_library_constants(self):
        pkix = self.by_oid["1.3.6.1.5.5.7.3.1"]
        self.assertEqual(pkix["oid_role"], "library-constant")
        self.assertEqual(pkix["namespace"], "standard")
        self.assertIn("BouncyCastle.Crypto.dll", pkix["sources"])

    def test_wifi_scan_columns_are_curated(self):
        ssid = self.by_oid["1.3.6.1.4.1.1347.40.39.1.1.1.1"]
        self.assertEqual(ssid["semantic_name"], "access_point_ssid")
        self.assertEqual(ssid["prefix_symbols"], "kmnetEnhancedWSDssl")
        self.assertEqual(
            self.by_oid["1.3.6.1.4.1.1347.40.43.1.1.1.1"][
                "semantic_name"
            ],
            "wifi_capable_1",
        )

    def test_known_oid_relationships(self):
        sleep = self.by_oid["1.3.6.1.4.1.1347.43.5.1.1.23"]
        self.assertEqual(sleep["symbols"], "kcprtSleepTimer")
        self.assertEqual(sleep["config_descendant_items"], "1")

        wifi = self.by_oid["1.3.6.1.4.1.1347.40.42.1.1.1.1"]
        self.assertEqual(wifi["prefix_symbols"], "kmnetHTTPSenable")
        self.assertEqual(wifi["config_items"], "142")

        fax = self.by_oid["1.3.6.1.4.1.1347.45.8.1.1.14"]
        self.assertEqual(
            set(fax["symbols"].split("|")),
            {"INFO_FAXDEVICEISEXIST", "kmFaxDeviceExist"},
        )
        self.assertIn("fax-ini", fax["name_sources"])

    def test_namespace_roots(self):
        self.assertEqual(
            self.by_oid["1.3.6.1.2.1"]["namespace"], "standard"
        )
        self.assertEqual(
            self.by_oid["1.3.6.1.4.1.1347"]["namespace"], "kyocera"
        )
        self.assertEqual(self.by_oid["1.3.6.1.2.1"]["oid_role"], "root")
        self.assertEqual(
            self.by_oid["1.3.6.1.4.1.1347"]["oid_role"], "root"
        )


if __name__ == "__main__":
    unittest.main()
