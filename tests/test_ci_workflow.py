import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class CiWorkflowTests(unittest.TestCase):
    def test_ci_runs_tests_without_building_release_artifacts(self):
        workflow = (
            ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        for expected in (
            "pull_request:",
            "workflow_dispatch:",
            'branches:',
            '- "3.10"',
            '- "3.12"',
            "python -m unittest discover -s tests -v",
            "python tools/check_publication.py",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, workflow)
        for unexpected in (
            "python -m build",
            "python tools/build_deb.py",
            "actions/upload-artifact",
        ):
            with self.subTest(unexpected=unexpected):
                self.assertNotIn(unexpected, workflow)

    def test_tag_release_builds_verified_artifacts(self):
        workflow = (
            ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")
        for expected in (
            "tags:",
            '- "v*"',
            "workflow_dispatch:",
            "release_tag:",
            'python tools/release.py check --tag "${RELEASE_TAG}"',
            "python -m unittest discover -s tests -v",
            "python -m build",
            "python tools/build_deb.py --output-dir dist/deb",
            "python tools/check_publication.py",
            "actions/upload-artifact@v4",
            "gh release create",
            "update.json",
            "gh release upload updater update.json --clobber",
            'gh release edit "${RELEASE_TAG}" --latest',
            "dist/*.whl",
            "dist/*.tar.gz",
            "dist/deb/*.deb",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, workflow)
        self.assertNotIn("pull_request:", workflow)


if __name__ == "__main__":
    unittest.main()
