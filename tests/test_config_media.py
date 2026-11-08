import csv
import unittest
from pathlib import Path

from kyocera_monitor.config_media import (
    MEDIA_TYPE_NAMES,
    PAPER_SIZE_NAMES,
    PAPER_WEIGHT_NAMES,
)


class ConfigMediaTests(unittest.TestCase):
    def test_public_table_matches_runtime_labels(self):
        path = (
            Path(__file__).resolve().parent.parent
            / "docs"
            / "reverse-engineering"
            / "data"
            / "clienttool-media-values.tsv"
        )
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        by_kind = {
            kind: {
                int(row["value"]): row["zh_hans"]
                for row in rows
                if row["kind"] == kind
            }
            for kind in ("paper_size", "media_type", "paper_weight")
        }
        self.assertEqual(by_kind["paper_size"], PAPER_SIZE_NAMES)
        self.assertEqual(by_kind["media_type"], MEDIA_TYPE_NAMES)
        self.assertEqual(by_kind["paper_weight"], PAPER_WEIGHT_NAMES)
        self.assertNotIn(19, PAPER_SIZE_NAMES)


if __name__ == "__main__":
    unittest.main()
