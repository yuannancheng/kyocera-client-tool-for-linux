import tempfile
import unittest
from pathlib import Path

from tools.release import (
    ReleaseError,
    bump_version,
    read_project_version,
    verify_tag,
    write_project_version,
)


class ReleaseVersionTests(unittest.TestCase):
    def test_current_project_version_is_semver(self):
        root = Path(__file__).resolve().parent.parent
        self.assertRegex(
            read_project_version(root / "pyproject.toml"),
            r"^[0-9]+\.[0-9]+\.[0-9]+$",
        )

    def test_release_tags_must_match_project_version(self):
        verify_tag("0.4.0", "v0.4.0")
        with self.assertRaises(ReleaseError):
            verify_tag("0.4.0", "v0.3.9")
        with self.assertRaises(ReleaseError):
            verify_tag("0.4.0", "0.4.0")

    def test_bump_resets_lower_components(self):
        self.assertEqual(bump_version("1.2.3", "major"), "2.0.0")
        self.assertEqual(bump_version("1.2.3", "minor"), "1.3.0")
        self.assertEqual(bump_version("1.2.3", "patch"), "1.2.4")

    def test_write_only_changes_the_project_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pyproject.toml"
            path.write_text(
                "[build-system]\n"
                'requires = ["setuptools>=68"]\n'
                "\n"
                "[project]\n"
                'name = "example"\n'
                'version = "1.2.3"\n'
                'description = "keep me"\n',
                encoding="utf-8",
            )
            write_project_version(path, "1.3.0")
            text = path.read_text(encoding="utf-8")
            self.assertIn('version = "1.3.0"', text)
            self.assertIn('description = "keep me"', text)
            self.assertEqual(read_project_version(path), "1.3.0")


if __name__ == "__main__":
    unittest.main()
