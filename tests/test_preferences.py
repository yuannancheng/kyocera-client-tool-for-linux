import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from kyocera_monitor.preferences import (
    SettingsError,
    SettingsStore,
    merge_scan_payload,
    normalize_settings,
)
from kyocera_monitor.reporting import counters_csv


class SettingsTests(unittest.TestCase):
    def test_defaults_and_round_trip_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)
            initial = store.load()
            self.assertEqual(initial["presets"], [])
            self.assertTrue(Path(initial["scan_directory"]).is_absolute())

            settings = {
                "version": 1,
                "scan_directory": str(Path(tmp) / "scans"),
                "presets": [
                    {
                        "id": "a4-color",
                        "name": "A4 彩扫",
                        "color": "FULL_COLOR",
                        "resolution": "RESOLUTION_300X300",
                        "original_image": "TEXT_AND_PHOTO",
                        "max_pages": 2,
                        "output_format": "pdf",
                    }
                ],
            }
            saved = store.save(settings)
            self.assertEqual(store.load(), saved)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text())["version"], 1)

    def test_invalid_settings_fail_closed(self):
        cases = (
            {"scan_directory": "relative/path", "presets": []},
            {
                "scan_directory": "/tmp",
                "presets": [
                    {
                        "id": "bad id",
                        "name": "x",
                        "output_format": "png",
                        "max_pages": 1,
                    }
                ],
            },
            {
                "scan_directory": "/tmp",
                "presets": [
                    {
                        "id": "same",
                        "name": "x",
                        "output_format": "png",
                        "max_pages": 1,
                    },
                    {
                        "id": "same",
                        "name": "y",
                        "output_format": "png",
                        "max_pages": 1,
                    },
                ],
            },
            {
                "scan_directory": "/tmp",
                "presets": [
                    {
                        "id": "x",
                        "name": "x",
                        "output_format": "webp",
                        "max_pages": 1,
                    }
                ],
            },
        )
        for settings in cases:
            with self.subTest(settings=settings):
                with self.assertRaises(SettingsError):
                    normalize_settings(settings)

    def test_preset_values_fill_missing_scan_fields_only(self):
        merged = merge_scan_payload(
            {
                "host": "192.0.2.1",
                "preset_id": "quick",
                "save_to_folder": True,
                "color": "GRAYSCALE",
            },
            {
                "id": "quick",
                "name": "Quick",
                "color": "FULL_COLOR",
                "resolution": "RESOLUTION_300X300",
                "original_image": "TEXT",
                "max_pages": 2,
                "output_format": "pdf",
            },
        )
        self.assertEqual(merged["color"], "GRAYSCALE")
        self.assertEqual(merged["resolution"], "RESOLUTION_300X300")
        self.assertEqual(merged["output_format"], "pdf")
        self.assertNotIn("preset_id", merged)
        self.assertNotIn("save_to_folder", merged)


class CounterExportTests(unittest.TestCase):
    def test_export_includes_errors_and_escapes_formula_prefixes(self):
        data = counters_csv(
            [
                {
                    "device": "192.0.2.1",
                    "collected_at": "2026-11-01T00:00:00+00:00",
                    "error": None,
                    "snapshot": {
                        "model": "=MA2000w",
                        "serial": "REDACTED",
                        "firmware": "1.0",
                        "normal": True,
                        "toner_level": 75,
                        "snmp": {"page_count": 129, "scan_count": 3},
                        "kgetobj_known": {
                            "drum_counter": {"value": 129},
                            "drum_counter_max": {"value": 10000},
                        },
                    },
                },
                {
                    "device": "192.0.2.2",
                    "collected_at": "2026-11-01T00:00:01+00:00",
                    "error": "offline",
                    "snapshot": None,
                },
            ]
        ).decode("utf-8-sig")
        self.assertIn("'=MA2000w", data)
        self.assertIn("129,3,129,10000", data)
        self.assertIn("offline", data)


if __name__ == "__main__":
    unittest.main()
