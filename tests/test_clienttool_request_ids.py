"""Checks for the KMUTLMNT symbolic request-ID extractor."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import clienttool_request_ids  # noqa: E402
from clienttool_oids import PEImage  # noqa: E402


BINARY = ROOT / "Kyocera" / "ClientTool" / "KMUTLMNT.exe"


class RequestIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not BINARY.is_file():
            raise unittest.SkipTest("Kyocera/ClientTool/KMUTLMNT.exe is not present")

    def test_known_request_ids(self) -> None:
        image = PEImage(BINARY)
        digest = hashlib.sha256(image.data).hexdigest()
        self.assertEqual(digest, clienttool_request_ids.EXPECTED_SHA256)
        mapping = clienttool_request_ids.extract(image)
        self.assertEqual(len(mapping), 177)
        self.assertEqual(
            mapping["MNTE_REQUEST_ID_HIGH_ALTITUDE_MODE"], 0x3001E
        )
        self.assertEqual(
            mapping["MNTE_REQUEST_ID_DRUM_REFRESH"], 0x60003
        )
        self.assertEqual(
            mapping["MNTE_REQUEST_ID_DRUM_COUNTER_RESET"], 0x6000F
        )
        self.assertEqual(
            mapping["MNTE_REQUEST_ID_RESTORE_FACTORY_INITIALIZE"], 0x30031
        )


if __name__ == "__main__":
    unittest.main()
