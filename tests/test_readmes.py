import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ReadmeTests(unittest.TestCase):
    def test_chinese_is_default_and_links_to_english(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        english = (ROOT / "README.en.md").read_text(encoding="utf-8")
        self.assertIn("简体中文 | [English](README.en.md)", readme)
        self.assertIn("[简体中文](README.md) | English", english)
        for text in (readme, english):
            self.assertIn("kyocera-monitor --check-update", text)
            self.assertIn("tools/release.py", text)
            self.assertIn("Python", text)


if __name__ == "__main__":
    unittest.main()
