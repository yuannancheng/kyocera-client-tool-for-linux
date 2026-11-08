import json
import unittest
from pathlib import Path
from unittest import mock

from kyocera_monitor import updates
from kyocera_monitor.updates import (
    UpdateCheckError,
    UpdateChecker,
    current_version,
    fetch_update_metadata,
    is_newer_version,
    project_version_from_pyproject,
)


class FakeResponse:
    def __init__(self, payload=b"", status=200):
        self.payload = payload
        self.status = status

    def read(self, _limit):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class VersionComparisonTests(unittest.TestCase):
    def test_versions_compare_numerically(self):
        self.assertTrue(is_newer_version("0.10.0", "0.9.9"))
        self.assertTrue(is_newer_version("v1.0.0", "0.99.99"))
        self.assertFalse(is_newer_version("0.3.1", "v0.3.1"))
        self.assertFalse(is_newer_version("0.2.9", "0.3.0"))

    def test_invalid_versions_fail_closed(self):
        for value in ("1.2", "01.2.3", "latest"):
            with self.subTest(value=value):
                with self.assertRaises(UpdateCheckError):
                    is_newer_version(value, "0.3.1")

    def test_source_version_matches_pyproject(self):
        root = Path(__file__).resolve().parent.parent
        expected = project_version_from_pyproject(root / "pyproject.toml")
        self.assertIsNotNone(expected)
        self.assertEqual(current_version(), expected)


class UpdateMetadataTests(unittest.TestCase):
    def test_fetches_and_validates_metadata(self):
        payload = json.dumps(
            {
                "version": "v0.4.0",
                "htmlUrl": "https://github.com/example/repo/releases/tag/v0.4.0",
            }
        ).encode()
        with mock.patch.object(
            updates,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            self.assertEqual(
                fetch_update_metadata("https://example.invalid/update.json"),
                (
                    "0.4.0",
                    "https://github.com/example/repo/releases/tag/v0.4.0",
                ),
            )

    def test_rejects_unsafe_or_malformed_metadata(self):
        cases = (
            b'{"version":"0.4.0","htmlUrl":"javascript:alert(1)"}',
            b'{"version":"latest","htmlUrl":"https://example.com/release"}',
            b"not json",
            b"[]",
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with mock.patch.object(
                    updates,
                    "urlopen",
                    return_value=FakeResponse(payload),
                ):
                    with self.assertRaises(UpdateCheckError):
                        fetch_update_metadata(
                            "https://example.invalid/update.json"
                        )

    def test_rejects_oversized_payload(self):
        payload = b"{" + b" " * updates.MAX_UPDATE_BYTES + b"}"
        with mock.patch.object(
            updates,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            with self.assertRaises(UpdateCheckError):
                fetch_update_metadata("https://example.invalid/update.json")

    def test_rejects_non_http_update_source(self):
        with self.assertRaises(UpdateCheckError):
            fetch_update_metadata("file:///etc/passwd")


class UpdateCheckerTests(unittest.TestCase):
    def test_result_is_cached_and_force_bypasses_cache(self):
        calls = []
        now = [100.0]

        def fetcher(_url):
            calls.append(now[0])
            return "0.4.0", "https://github.com/example/repo/releases/tag/v0.4.0"

        checker = UpdateChecker(
            current="0.3.1",
            fetcher=fetcher,
            cache_seconds=60,
            clock=lambda: now[0],
            wall_clock=lambda: 1_700_000_000.0,
        )
        first = checker.check()
        now[0] += 5
        second = checker.check()
        third = checker.check(force=True)
        self.assertTrue(first.update_available)
        self.assertTrue(second.cached)
        self.assertFalse(third.cached)
        self.assertEqual(len(calls), 2)
        self.assertTrue(first.checked_at.startswith("2023-"))

    def test_older_remote_version_is_not_an_update(self):
        checker = UpdateChecker(
            current="1.0.0",
            fetcher=lambda _url: (
                "0.9.9",
                "https://github.com/example/repo/releases/tag/v0.9.9",
            ),
        )
        self.assertFalse(checker.check().update_available)

    def test_invalid_current_version_is_rejected(self):
        with self.assertRaises(UpdateCheckError):
            UpdateChecker(current="development")

    def test_does_not_contact_network_during_construction(self):
        calls = []
        checker = UpdateChecker(
            current="0.3.1",
            fetcher=lambda url: calls.append(url) or ("0.3.1", "https://x.test"),
        )
        self.assertEqual(calls, [])
        self.assertEqual(checker.current, "0.3.1")


if __name__ == "__main__":
    unittest.main()
