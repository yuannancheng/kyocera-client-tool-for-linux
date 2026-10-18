import unittest
from pathlib import Path

from tools.clienttool_config_offsets import (
    MODEL_SOURCE,
    OID_TABLE,
    build_rows,
    format_tsv,
)

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = (
    ROOT
    / "docs"
    / "reverse-engineering"
    / "data"
    / "clienttool-config-offsets.tsv"
)


@unittest.skipUnless(
    MODEL_SOURCE.exists(), "Ghidra KMUTLCFG export is not present"
)
class ClientToolConfigOffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = build_rows(MODEL_SOURCE, OID_TABLE)
        cls.by_id = {int(row["item_id"]): row for row in cls.rows}

    def test_every_object_has_a_model_offset(self):
        self.assertEqual(len(self.rows), 147)
        self.assertTrue(all(row["status"] == "mapped" for row in self.rows))

    def test_known_offsets_match_the_reverse_engineered_fields(self):
        expected = {
            1: "0x0010",   # Sleep time
            2: "0x0004",   # Auto error clear
            3: "0x0008",   # Auto error clear timeout
            4: "0x0014",   # Power off timer
            50: "0x0018",  # Quiet mode
            52: "0x2ffc",  # Form feed timeout
            59: "0x4550",  # IPv4 address
            60: "0x4654",  # Subnet mask
            61: "0x4758",  # Default gateway
            65: "0x486c",  # SNMP read community
            66: "0x4970",  # SNMP write community
            144: "0x3c90", # Wi-Fi SSID
        }
        for item_id, offset in expected.items():
            self.assertEqual(self.by_id[item_id]["primary_offset"], offset)

    def test_generated_tsv_matches_checked_in_data(self):
        self.assertEqual(
            format_tsv(self.rows), EXPECTED.read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
