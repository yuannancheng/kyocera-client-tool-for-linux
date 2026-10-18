import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"

sys.path.insert(0, str(ROOT / "tools"))

import clienttool_job_oids  # noqa: E402


class ClientToolJobOidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DATA / "clienttool-job-oids.tsv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle, delimiter="\t"))
        cls.by_symbol = {row["symbol"]: row for row in cls.rows}

    def test_checked_in_table_matches_the_expander(self):
        rows = clienttool_job_oids.expand_job_oids(
            clienttool_job_oids.DEFAULT_XML
        )
        self.assertEqual(
            clienttool_job_oids.format_tsv(rows),
            (DATA / "clienttool-job-oids.tsv").read_text(encoding="utf-8"),
        )

    def test_every_row_has_a_unique_absolute_oid(self):
        self.assertEqual(len(self.rows), 205)
        oids = [row["oid"] for row in self.rows]
        self.assertEqual(len(set(oids)), 205)
        for oid in oids:
            self.assertTrue(oid.startswith("1.3.6.1.4.1.1347."), oid)
        kinds = {}
        for row in self.rows:
            kinds[row["oid_kind"]] = kinds.get(row["oid_kind"], 0) + 1
        self.assertEqual(kinds, {"absolute": 5, "relative": 200})

    def test_known_job_columns(self):
        self.assertEqual(
            self.by_symbol["kmJobGeneralIndex"]["oid"],
            "1.3.6.1.4.1.1347.47.1.1.1.1",
        )
        self.assertEqual(
            self.by_symbol["kmPrintJobStatusCount"]["oid"],
            "1.3.6.1.4.1.1347.47.1.1.1.2",
        )
        self.assertEqual(
            self.by_symbol["kmPrintJobStatusCondition"]["oid"],
            "1.3.6.1.4.1.1347.47.2.1.1.6",
        )
        self.assertEqual(
            self.by_symbol["kmFaxDeviceExist"]["oid"],
            "1.3.6.1.4.1.1347.45.8.1.1.14",
        )
        self.assertEqual(
            self.by_symbol["kmAddrBookSecurityAuth"]["oid"],
            "1.3.6.1.4.1.1347.42.23.1.8.0",
        )

    def test_relative_oid_without_parent_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.xml"
            path.write_text('<root><child oid="1"/></root>', encoding="utf-8")
            with self.assertRaises(ValueError):
                clienttool_job_oids.expand_job_oids(path)


if __name__ == "__main__":
    unittest.main()
