import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"

sys.path.insert(0, str(ROOT / "tools"))

import clienttool_oid_sources  # noqa: E402


class ClientToolOidSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DATA / "clienttool-oid-mapping-sources.tsv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle, delimiter="\t"))
        cls.by_source = {row["source"]: row for row in cls.rows}

    def test_checked_in_inventory_matches_the_scanner(self):
        rows = clienttool_oid_sources.inventory(
            clienttool_oid_sources.DEFAULT_ROOT
        )
        self.assertEqual(
            clienttool_oid_sources.format_tsv(rows),
            (DATA / "clienttool-oid-mapping-sources.tsv").read_text(
                encoding="utf-8"
            ),
        )

    def test_both_snmp_oid_files_are_absolute_tables(self):
        snmp_rows = [
            row for row in self.rows if row["kind"] == "prefix-symbol"
        ]
        self.assertEqual(len(snmp_rows), 2)
        for row in snmp_rows:
            self.assertEqual(row["relative_oids"], "0")

    def test_job_tree_is_hierarchical(self):
        row = self.by_source[
            "Kyocera/ClientTool/WFH/remotefax/addins/Device/"
            "Device.DeviceJobs/conf/JobSnmpOid.xml"
        ]
        self.assertEqual(row["kind"], "hierarchical-job")
        self.assertEqual(row["oid_elements"], "205")
        self.assertEqual(row["relative_oids"], "200")


if __name__ == "__main__":
    unittest.main()
