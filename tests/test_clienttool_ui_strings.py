import unittest
from pathlib import Path

from tools.clienttool_ui_strings import format_tsv, read_ui_entries

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "Kyocera" / "ClientTool" / "KMUTLCFG.exe"
RES = ROOT / "Kyocera" / "ClientTool" / "LANG" / "en" / "KMUTLCFGRes.dll"
EXPECTED = (
    ROOT / "docs" / "reverse-engineering" / "data" / "clienttool-ui-controls.tsv"
)


class ClientToolUiStringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = read_ui_entries(EXE, RES)

    def test_label_table_maps_known_controls_without_text(self):
        labels = {
            entry.control_id: entry
            for entry in self.entries
            if entry.kind == "label"
        }
        for control_id in (0x03E8, 0x03E9, 0x03EA, 0x0455, 0x04CF, 0x04DA):
            self.assertTrue(labels[control_id].text_present)
            self.assertGreater(labels[control_id].text_length, 0)
        self.assertFalse(hasattr(labels[0x03E8], "text"))

    def test_combo_options_are_in_resource_order(self):
        combos: dict[int, list] = {}
        for entry in self.entries:
            if entry.kind == "combo_option":
                combos.setdefault(entry.control_id, []).append(entry)
        self.assertEqual(len(combos[0x0463]), 15)
        self.assertEqual([entry.option_index for entry in combos[0x0463]], list(range(15)))
        self.assertEqual(len(combos[0x03F6]), 7)
        self.assertEqual(len(combos[0x03F7]), 5)
        self.assertEqual(len(combos[0x04AB]), 4)
        self.assertTrue(all(entry.text_present for entry in combos[0x0463]))

    def test_generated_tsv_matches_checked_in_data(self):
        self.assertEqual(format_tsv(self.entries), EXPECTED.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
