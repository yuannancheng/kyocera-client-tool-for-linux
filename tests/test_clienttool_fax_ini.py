import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"

sys.path.insert(0, str(ROOT / "tools"))

import clienttool_fax_ini  # noqa: E402


class ClientToolFaxIniTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DATA / "clienttool-fax-snmp-oids.tsv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle, delimiter="\t"))
        cls.by_name = {row["name"]: row for row in cls.rows}

    def test_checked_in_table_matches_the_parser(self):
        rows = clienttool_fax_ini.parse_ini(clienttool_fax_ini.DEFAULT_INI)
        self.assertEqual(
            clienttool_fax_ini.format_tsv(rows),
            (DATA / "clienttool-fax-snmp-oids.tsv").read_text(
                encoding="utf-8"
            ),
        )

    def test_counts_and_multi_oid_rows(self):
        self.assertEqual(len(self.rows), 144)
        self.assertEqual(len({row["oid"] for row in self.rows}), 108)
        self.assertEqual(len(self.by_name), 116)
        self.assertGreater(len(self.rows), len(self.by_name))

    def test_known_fax_names(self):
        self.assertEqual(
            self.by_name["INFO_MODELNAME"]["oid"],
            "1.3.6.1.4.1.1347.43.5.1.1.1",
        )
        self.assertEqual(
            self.by_name["INFO_FAXDEVICEISEXIST"]["oid"],
            "1.3.6.1.4.1.1347.45.8.1.1.14",
        )
        self.assertEqual(
            self.by_name["INFO_FAXPORTNUM"]["oid"],
            "1.3.6.1.4.1.1347.45.8.1.1.18",
        )


if __name__ == "__main__":
    unittest.main()
