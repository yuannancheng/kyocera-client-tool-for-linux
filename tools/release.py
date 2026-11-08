#!/usr/bin/env python3
"""Manage the single project version and verify release tags."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
PROJECT_VERSION_RE = re.compile(
    r'(?ms)(^\[project\]\s*$.*?^version\s*=\s*")([^"]+)(")'
)


class ReleaseError(ValueError):
    """Raised when version or tag validation fails."""


def read_project_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = PROJECT_VERSION_RE.search(text)
    if match is None:
        raise ReleaseError(f"{path} has no [project] version")
    version = match.group(2)
    if VERSION_RE.fullmatch(version) is None:
        raise ReleaseError(
            f"project version must be MAJOR.MINOR.PATCH, got {version!r}"
        )
    return version


def bump_version(version: str, part: str) -> str:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise ReleaseError(
            f"project version must be MAJOR.MINOR.PATCH, got {version!r}"
        )
    major, minor, patch = (int(value) for value in match.groups())
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    elif part == "patch":
        patch += 1
    else:
        raise ReleaseError("version part must be major, minor or patch")
    return f"{major}.{minor}.{patch}"


def write_project_version(path: Path, version: str) -> None:
    if VERSION_RE.fullmatch(version) is None:
        raise ReleaseError(
            f"project version must be MAJOR.MINOR.PATCH, got {version!r}"
        )
    text = path.read_text(encoding="utf-8")
    match = PROJECT_VERSION_RE.search(text)
    if match is None:
        raise ReleaseError(f"{path} has no [project] version")
    updated = text[: match.start(2)] + version + text[match.end(2) :]
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, path.stat().st_mode & 0o777)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def verify_tag(version: str, tag: str) -> None:
    expected = f"v{version}"
    if tag != expected:
        raise ReleaseError(
            f"release tag {tag!r} does not match project version "
            f"{version!r}; expected {expected!r}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        type=Path,
        default=ROOT / "pyproject.toml",
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="print the current version")

    check = subparsers.add_parser(
        "check",
        help="verify that a vX.Y.Z tag matches pyproject.toml",
    )
    check.add_argument("--tag", required=True, help="Git tag, for example v0.4.0")

    bump = subparsers.add_parser(
        "bump",
        help="increment pyproject.toml without creating a commit or tag",
    )
    bump.add_argument("part", choices=("major", "minor", "patch"))
    bump.add_argument(
        "--dry-run",
        action="store_true",
        help="print the next version without changing pyproject.toml",
    )

    args = parser.parse_args(argv)
    try:
        version = read_project_version(args.project)
        if args.command == "version":
            print(version)
        elif args.command == "check":
            verify_tag(version, args.tag)
            print(f"release tag {args.tag} matches project version {version}")
        else:
            next_version = bump_version(version, args.part)
            if not args.dry_run:
                write_project_version(args.project, next_version)
            print(next_version)
    except (OSError, ReleaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
