#!/usr/bin/env python3
"""Extract symbolic-to-numeric MNTE request IDs from KMUTLMNT.exe.

The table is stored as adjacent (string pointer, numeric id) pairs in .data.
This tool only reads the PE image and fails closed on a different build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from clienttool_oids import PEImage


EXPECTED_SHA256 = (
    "60d60c35152413dbec717458797310ba92d30091f006ebb44d399582515336b2"
)
PREFIX = "MNTE_REQUEST_ID_"


def extract(image: PEImage) -> dict[str, int]:
    data_section = next((s for s in image.sections if s.name == ".data"), None)
    if data_section is None:
        raise ValueError("missing .data section")
    start = data_section.raw_pointer
    end = start + data_section.raw_size
    mapping: dict[str, int] = {}
    for offset in range(start, end - 8, 4):
        pointer, value = struct.unpack_from("<II", image.data, offset)
        if not 0x10000 <= value <= 0x6FFFF:
            continue
        name = image.c_string(pointer)
        if not name or not name.startswith(PREFIX):
            continue
        previous = mapping.get(name)
        if previous is not None and previous != value:
            raise ValueError(
                f"ambiguous mapping for {name}: 0x{previous:x} vs 0x{value:x}"
            )
        mapping[name] = value
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "binary",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "Kyocera"
        / "ClientTool"
        / "KMUTLMNT.exe",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.binary.is_file():
        print(f"error: {args.binary} does not exist", file=sys.stderr)
        return 2
    try:
        image = PEImage(args.binary)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    digest = hashlib.sha256(image.data).hexdigest()
    if digest != EXPECTED_SHA256:
        print(
            f"error: unexpected KMUTLMNT.exe SHA-256 {digest}; refusing "
            "build-specific .data scan",
            file=sys.stderr,
        )
        return 3
    try:
        mapping = extract(image)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if args.json:
        json.dump(
            {
                "source": str(args.binary),
                "sha256": digest,
                "requests": mapping,
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        print()
    else:
        print("request_id\tnumeric_id")
        for name, value in sorted(mapping.items(), key=lambda item: (item[1], item[0])):
            print(f"{name}\t0x{value:08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
