import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"
EXE = ROOT / "Kyocera" / "ClientTool" / "KMUTLCFG.exe"

sys.path.insert(0, str(ROOT / "tools"))

import clienttool_dialogs  # noqa: E402


class ClientToolDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DATA / "clienttool-dialogs.tsv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle, delimiter="\t"))

    def test_main_dialog_owns_the_mapped_controls(self):
        main = {
            row["control_id"]: row
            for row in self.rows
            if row["dialog"] == "0x006b"
        }
        self.assertEqual(main["0x0411"]["class"], "#129")
        self.assertEqual(main["0x0410"]["class"], "msctls_updown32")
        self.assertEqual(main["0x0403"]["text_present"], "1")
        self.assertGreater(int(main["0x0403"]["text_length"]), 0)
        self.assertEqual(main["0x04ab"]["class"], "#133")

    def test_dialog_metadata_has_no_vendor_text(self):
        self.assertNotIn("dialog_caption", self.rows[0])
        self.assertNotIn("text", self.rows[0])
        controls = {
            (row["dialog"], row["control_id"]): row for row in self.rows
        }
        self.assertEqual(controls[("0x00d0", "0x04cf")]["text_present"], "1")
        self.assertEqual(controls[("0x00d0", "0x04d1")]["text_present"], "1")
        self.assertEqual(controls[("0x008d", "0x043f")]["text_present"], "1")
        self.assertEqual(controls[("0x008d", "0x041e")]["class"], "#129")

    def test_checked_in_table_matches_the_extractor(self):
        controls = clienttool_dialogs.read_dialogs(EXE)
        self.assertEqual(
            clienttool_dialogs.format_tsv(controls),
            (DATA / "clienttool-dialogs.tsv").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
