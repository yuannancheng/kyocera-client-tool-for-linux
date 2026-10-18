import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"


def read_tsv(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class ClientToolControlOidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controls = read_tsv("clienttool-control-oids.tsv")
        cls.offsets = {
            row["item_id"]: row
            for row in read_tsv("clienttool-config-offsets.tsv")
        }
        cls.labels = {
            row["control_id"]: row
            for row in read_tsv("clienttool-ui-controls.tsv")
            if row["kind"] == "label"
        }

    def test_control_offsets_match_the_object_offset_table(self):
        self.assertEqual(len(self.controls), 69)
        for row in self.controls:
            if not row["item_id"]:
                continue
            expected = self.offsets[row["item_id"]]
            self.assertEqual(row["oid"], expected["oid"])
            allowed = {expected["primary_offset"].lower()}
            for value in expected["extra_offsets"].split(";"):
                if value:
                    allowed.add(value.lower())
            self.assertIn(row["model_offset"].lower(), allowed)

    def test_control_resources_have_redacted_text_metadata(self):
        self.assertEqual(self.labels["0x03ea"]["text_present"], "1")
        self.assertEqual(self.labels["0x0455"]["text_present"], "1")
        self.assertEqual(self.labels["0x04cf"]["text_present"], "1")
        self.assertNotIn("text", self.labels["0x03ea"])

    def test_known_control_to_oid_pairs(self):
        by_control = {
            (row["dialog"], row["control_id"]): row for row in self.controls
        }
        self.assertEqual(
            by_control[("0x006b", "0x03f2")]["oid"], "43.5.1.1.23.1"
        )
        self.assertEqual(
            by_control[("0x006b", "0x0463")]["oid"], "42.5.1.1.43.1"
        )
        self.assertEqual(
            by_control[("0x006b", "0x0455")]["oid"], "1001.2.1.1.1.14.1"
        )
        self.assertEqual(
            by_control[("0x006b", "0x0411")]["oid"], "43.5.1.1.22.1"
        )
        self.assertEqual(
            by_control[("0x006b", "0x03f5")]["oid"], "43.8.1.1.4.1.1"
        )
        self.assertEqual(
            by_control[("0x006b", "0x03f8")]["oid"], "43.8.1.1.11.1.1"
        )
        self.assertEqual(
            by_control[("0x006b", "0x0474")]["oid"], "46.8.1.1.6.3.1"
        )

    def test_dialog_scoped_controls_do_not_collide(self):
        keys = {
            (row["dialog"], row["control_id"]) for row in self.controls
        }
        self.assertEqual(len(keys), len(self.controls))
        self.assertIn(("0x00d0", "0x04d4"), keys)
        self.assertIn(("0x008d", "0x041e"), keys)
        self.assertIn(("0x008e", "0x0456"), keys)

    def test_communication_page_network_mapping(self):
        by_control = {
            (row["dialog"], row["control_id"]): row for row in self.controls
        }
        self.assertEqual(
            by_control[("0x008d", "0x041e")]["oid"], "40.10.1.1.5.1"
        )
        self.assertEqual(
            by_control[("0x008d", "0x045e")]["oid"], "40.10.1.1.4.1"
        )
        self.assertEqual(
            by_control[("0x008d", "0x045f")]["oid"], "40.10.1.1.6.1"
        )
        self.assertEqual(
            by_control[("0x008d", "0x0460")]["oid"], "40.10.1.1.7.1"
        )

    def test_trap_page_recipients_and_event_fields(self):
        by_control = {
            (row["dialog"], row["control_id"]): row for row in self.controls
        }
        self.assertEqual(
            by_control[("0x008d", "0x042d")]["oid"],
            "1.3.6.1.2.1.11.30.0",
        )
        self.assertEqual(
            by_control[("0x008e", "0x0459")]["oid"], "40.26.5.1.7.1.1"
        )
        self.assertEqual(
            by_control[("0x008e", "0x042e")]["oid"], "40.26.5.1.4.1.1"
        )
        self.assertEqual(
            by_control[("0x008e", "0x0461")]["oid"], "40.26.5.1.2.1.1"
        )
        self.assertEqual(
            by_control[("0x008e", "0x0456")]["oid"], "40.26.5.1.7.1.2"
        )
        self.assertEqual(
            by_control[("0x008e", "0x0438")]["oid"], "40.26.5.1.5.1.2"
        )
        self.assertEqual(
            by_control[("0x008e", "0x043d")]["model_offset"], "0x51c8"
        )

    def test_wifi_status_page_fields(self):
        by_control = {
            (row["dialog"], row["control_id"]): row for row in self.controls
        }
        expected = {
            "0x04fa": ("0x3c88", "142", "40.42.1.1.1.1"),
            "0x04fb": ("0x3c90", "144", "40.42.1.1.4.1"),
            "0x04fc": ("0x3d94", "145", "40.42.1.1.5.1"),
            "0x04fd": ("0x3d98", "147", "40.42.1.1.6.1"),
            "0x04fe": ("0x3d9c", "146", "40.42.1.1.7.1"),
        }
        for control_id, (offset, item_id, oid) in expected.items():
            row = by_control[("0x00f3", control_id)]
            self.assertEqual(row["model_offset"], offset)
            self.assertEqual(row["item_id"], item_id)
            self.assertEqual(row["oid"], oid)
            self.assertEqual(row["confidence"], "verified")

    def test_volume_and_fax_notification_pages(self):
        by_control = {
            (row["dialog"], row["control_id"]): row for row in self.controls
        }
        expected = {
            ("0x00d1", "0x04d7"): ("0x3da0", "108", "45.8.1.1.11.4"),
            ("0x00d1", "0x04d8"): ("0x3da0", "108", "45.8.1.1.11.4"),
            ("0x00d1", "0x04da"): ("0x3da4", "109", "45.8.1.1.10.4"),
            ("0x00d1", "0x04db"): ("0x3da4", "109", "45.8.1.1.10.4"),
            ("0x00d2", "0x04dd"): ("0x3db0", "112", "45.10.3.1.2.4"),
            ("0x00d2", "0x04de"): ("0x3db4", "113", "45.10.3.1.3.4"),
            ("0x00d2", "0x04e0"): ("0x3db8", "114", "45.9.3.1.2.4"),
            ("0x00d2", "0x04e2"): ("0x3da8", "110", "45.10.3.1.1.4"),
            ("0x00d2", "0x04e3"): ("0x3dac", "111", "45.9.3.1.1.4"),
        }
        for key, (offset, item_id, oid) in expected.items():
            row = by_control[key]
            self.assertEqual(row["model_offset"], offset)
            self.assertEqual(row["item_id"], item_id)
            self.assertEqual(row["oid"], oid)
            self.assertEqual(row["confidence"], "inferred")


if __name__ == "__main__":
    unittest.main()
