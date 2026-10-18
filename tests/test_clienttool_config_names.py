import csv
import sys
import unittest
from pathlib import Path

from kyocera_monitor.config_vendor_names import VENDOR_NAMES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"

sys.path.insert(0, str(ROOT / "tools"))

import clienttool_config_names  # noqa: E402


class ClientToolConfigNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DATA / "clienttool-config-names.tsv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle, delimiter="\t"))
        cls.by_oid = {row["oid"]: row for row in cls.rows}

    def test_coverage_and_match_kinds(self):
        self.assertEqual(len(self.rows), 147)
        kinds = {}
        for row in self.rows:
            kinds[row["match"]] = kinds.get(row["match"], 0) + 1
        self.assertEqual(kinds, {"table": 127, "none": 20})

    def test_key_vendor_names(self):
        self.assertEqual(
            self.by_oid["42.5.1.1.43.1"]["vendor_name"], "kmOffModeTimer"
        )
        self.assertEqual(
            self.by_oid["42.5.9.1.3.1"]["vendor_name"],
            "kmOffModeSettingState",
        )
        self.assertEqual(
            self.by_oid["45.8.1.1.11.4"]["vendor_name"],
            "kmFaxDeviceSpkVolumeLevel",
        )
        self.assertEqual(
            self.by_oid["45.5.1.1.3.4"]["vendor_name"], "kmFaxPrivateName"
        )
        self.assertEqual(
            self.by_oid["45.10.2.1.1.1.4"]["vendor_name"],
            "kmFaxForwardEnable",
        )
        self.assertEqual(self.by_oid["1001.2.1.1.1.8.1"]["match"], "none")

    def test_generated_module_matches_the_table(self):
        expected = {
            row["oid"]: row["vendor_name"]
            for row in self.rows
            if row["vendor_name"]
        }
        self.assertEqual(VENDOR_NAMES, expected)

    def test_checked_in_table_matches_the_extractor(self):
        vendor_oids = clienttool_config_names.merge_vendor_oids(
            clienttool_config_names.DEFAULT_XMLS
        )
        rows = clienttool_config_names.build_rows(
            clienttool_config_names.OID_TABLE, vendor_oids
        )
        self.assertEqual(
            clienttool_config_names.format_tsv(rows),
            (DATA / "clienttool-config-names.tsv").read_text(
                encoding="utf-8"
            ),
        )

    def test_index_covers_both_xml_files(self):
        with (DATA / "clienttool-snmp-oid-index.tsv").open(
            newline="", encoding="utf-8"
        ) as handle:
            index = list(csv.DictReader(handle, delimiter="\t"))
        sources = {row["source"] for row in index}
        self.assertEqual(len(sources), 2)
        self.assertTrue(any("WIFI/wifisetup" in source for source in sources))
        self.assertTrue(any("WFH/remotefax" in source for source in sources))
        pairs = {(row["oid"], row["symbol"]) for row in index}
        self.assertIn(
            (
                "1.3.6.1.4.1.1347.45.8.1.1.14",
                "kmFaxDeviceExist",
            ),
            pairs,
        )
        self.assertIn(("1.3.6.1.4.1.1347.42.5.1.1.12", "kmTimeZone"), pairs)

    def test_checked_in_index_matches_the_extractor(self):
        rows = clienttool_config_names.build_vendor_index(
            clienttool_config_names.DEFAULT_XMLS
        )
        self.assertEqual(
            clienttool_config_names.format_vendor_index(rows),
            (DATA / "clienttool-snmp-oid-index.tsv").read_text(
                encoding="utf-8"
            ),
        )


if __name__ == "__main__":
    unittest.main()
