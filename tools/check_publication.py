#!/usr/bin/env python3
"""Check the public tree for release-blocking compliance problems.

This is a deterministic guardrail. It checks file presence, tracked paths and
the schema of public research tables. It cannot decide copyright ownership or
provide legal advice.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_SUFFIXES = {
    ".cab",
    ".dll",
    ".exe",
    ".key",
    ".msi",
    ".mtp",
    ".p12",
    ".pem",
    ".sys",
    ".zip",
}
FORBIDDEN_PATHS = {
    "analysis",
    "Kyocera",
    "tools/unpack_mtp.py",
    "tests/test_unpack_mtp.py",
}
FORBIDDEN_COLUMNS = {
    "sample_context",
    "text",
    "dialog_caption",
    "menu_description",
    "item_subject",
}
DATA_HEADERS = (
    "docs/reverse-engineering/data/clienttool-all-oids.tsv",
    "docs/reverse-engineering/data/clienttool-ui-controls.tsv",
    "docs/reverse-engineering/data/clienttool-dialogs.tsv",
    "docs/reverse-engineering/data/clienttool-maintenance-requests.tsv",
)


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=True,
        capture_output=True,
    )
    return [
        value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    ]


def _history_files(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "log", "HEAD", "--pretty=format:", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line for line in result.stdout.splitlines() if line}


def _header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle, delimiter="\t"))


def collect_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    for name in (
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "CONTRIBUTING.md",
        "docs/legal/compliance.md",
    ):
        if not (root / name).is_file():
            errors.append(f"missing required file: {name}")

    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    if "MIT License" not in license_text or "AS IS" not in license_text:
        errors.append("LICENSE is not the expected MIT text")

    readme = (root / "README.md").read_text(encoding="utf-8").lower()
    for phrase in (
        "not affiliated",
        "unofficial",
        "mit license",
        "warranty",
        "liability",
    ):
        if phrase not in readme:
            errors.append(f"README is missing compliance phrase: {phrase}")

    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("Kyocera/", "analysis/", "*.exe", "*.dll", "*.mtp"):
        if pattern not in ignore:
            errors.append(f".gitignore is missing pattern: {pattern}")

    try:
        tracked = [
            name for name in _tracked_files(root) if (root / name).is_file()
        ]
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append(f"cannot inspect tracked files: {exc}")
        tracked = []

    for name in tracked:
        path = Path(name)
        if any(
            name == forbidden or name.startswith(forbidden + "/")
            for forbidden in FORBIDDEN_PATHS
        ):
            errors.append(f"tracked local-only path: {name}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"tracked forbidden file type: {name}")

    for relative in DATA_HEADERS:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing public data table: {relative}")
            continue
        columns = set(_header(path))
        bad = sorted(columns & FORBIDDEN_COLUMNS)
        if bad:
            errors.append(
                f"{relative} still exposes vendor text columns: {', '.join(bad)}"
            )

    cipher_marker = "from cryptography.hazmat.primitives." + "ciphers"
    for name in tracked:
        if not name.endswith(".py"):
            continue
        text = (root / name).read_text(encoding="utf-8", errors="replace")
        if cipher_marker in text:
            errors.append(f"public tree contains package decryption code: {name}")

    return errors


def collect_history_errors(root: Path = ROOT) -> list[str]:
    """Return restricted paths that remain reachable in Git history."""
    errors: list[str] = []
    try:
        history = _history_files(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"cannot inspect Git history: {exc}"]
    for name in sorted(history):
        path = Path(name)
        if any(
            name == forbidden or name.startswith(forbidden + "/")
            for forbidden in FORBIDDEN_PATHS
        ):
            errors.append(f"history still contains local-only path: {name}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"history still contains forbidden file type: {name}")
    return errors


def main() -> int:
    errors = collect_errors()
    if "--history" in sys.argv[1:]:
        errors.extend(collect_history_errors())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("publication check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
