import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = (
    ROOT
    / "Kyocera"
    / "ClientTool"
    / "WIFI"
    / "wifisetup"
    / "WifiSetupToolModels.dll"
)

sys.path.insert(0, str(ROOT / "tools"))

import managed_constants  # noqa: E402


class ManagedConstantsTests(unittest.TestCase):
    def test_non_pe_input_is_rejected(self):
        with self.assertRaises(managed_constants.MetadataError):
            managed_constants.PeImage(b"not a PE image")

    @unittest.skipUnless(MODELS.exists(), "ClientTool sample is not present")
    def test_wifi_models_field_constants(self):
        rows = managed_constants.decode_constants(MODELS)
        values = {row["owner"]: row["value"] for row in rows}
        self.assertEqual(
            values["AccessPointsSSID"],
            "1.3.6.1.4.1.1347.40.39.1.1.1.1",
        )
        self.assertEqual(
            values["SetAccessPointPreSharedKey"],
            "1.3.6.1.4.1.1347.40.40.1.1.9.1",
        )
        self.assertEqual(
            values["CheckAPSetConfigurationStatus"],
            "1.3.6.1.4.1.1347.40.42.1.1.3.1",
        )
        self.assertEqual(values["WifiCapable1"], "1.3.6.1.4.1.1347.40.43.1.1.1.1")


if __name__ == "__main__":
    unittest.main()
