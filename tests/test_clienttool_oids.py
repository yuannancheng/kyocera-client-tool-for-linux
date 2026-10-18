"""Checks for the ClientTool static protocol-object extractor."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import clienttool_oids  # noqa: E402


CLIENTTOOL = ROOT / "Kyocera" / "ClientTool"


class ClientToolOidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (CLIENTTOOL / "KMUTLCFG.exe").is_file():
            raise unittest.SkipTest("Kyocera/ClientTool binaries are not present")

    def test_config_table_matches_analyzed_build(self) -> None:
        image = clienttool_oids.PEImage(CLIENTTOOL / "KMUTLCFG.exe")
        digest = hashlib.sha256(image.data).hexdigest()
        self.assertEqual(digest, clienttool_oids.EXPECTED_HASHES["config"])

        rows = clienttool_oids.read_config_rows(image)
        self.assertEqual(len(rows), 147)
        self.assertEqual([row["item_id"] for row in rows], list(range(1, 148)))

    def test_config_pjl_prefix_rule(self) -> None:
        image = clienttool_oids.PEImage(CLIENTTOOL / "KMUTLCFG.exe")
        rows = clienttool_oids.read_config_rows(image)
        for row in rows:
            expected = (
                f"#{row['oid']}"
                if row["oid"].startswith("1.3.6")
                else f"1.{row['oid']}"
            )
            self.assertEqual(row["pjl_object"], expected)

    def test_preset_table_and_scan_list(self) -> None:
        image = clienttool_oids.PEImage(CLIENTTOOL / "KMUTLPRE.exe")
        rows = clienttool_oids.read_preset_rows(image)
        self.assertEqual(len(rows), 56)
        oid_rows = [
            row for row in rows
            if row["oid_format"].startswith("1.3.6.1.4.1.1347.1001.1.")
        ]
        self.assertEqual(len(oid_rows), 36)
        self.assertEqual(rows[15]["oid_format"], "SavePath")
        self.assertEqual(rows[20]["oid_format"], "ImgPos")
        self.assertEqual(
            clienttool_oids.read_preset_list(image),
            [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13],
        )


if __name__ == "__main__":
    unittest.main()
