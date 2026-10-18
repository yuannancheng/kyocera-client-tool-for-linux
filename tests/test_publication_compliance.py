import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_publication  # noqa: E402


class PublicationComplianceTests(unittest.TestCase):
    def test_public_tree_has_no_release_blocking_findings(self):
        self.assertEqual(check_publication.collect_errors(ROOT), [])


if __name__ == "__main__":
    unittest.main()
