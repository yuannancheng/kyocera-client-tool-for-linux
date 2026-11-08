#!/usr/bin/env python3
"""Extract official paper-size and media-type labels from Client Tool 1.4.11.2.

The output is the compact public interface dictionary used by the Linux UI.
It contains only the labels required to render device values and does not copy
the vendor resource files.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clienttool_oids import PEImage  # noqa: E402
from clienttool_ui_strings import load_string_resources  # noqa: E402


EXPECTED_HASHES = {
    "exe": "63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea",
    "zh_hans": "ae3b8ee53860f235fa8f180c23b3aca382af6f8e0f45fe79131b5a5210abcd96",
}
LABEL_NORMALIZATIONS = {
    "216 x 340 毫米": "216 × 340 mm",
    "自定义尺寸...": "自定义尺寸",
}

PAPER_SIZE_TABLE = 0x00497458
PAPER_SIZE_ENTRY_SIZE = 6 * 4
MEDIA_TYPE_TABLE = 0x00497C68
MEDIA_TYPE_ENTRY_SIZE = 7 * 4


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_u32(image: PEImage, address: int) -> int:
    offset = image.file_offset(address)
    if offset is None:
        raise ValueError(f"unmapped address 0x{address:08x}")
    return struct.unpack_from("<I", image.data, offset)[0]


def _read_table(
    image: PEImage,
    address: int,
    entry_size: int,
    terminator: tuple[int, int],
) -> list[tuple[int, ...]]:
    rows: list[tuple[int, ...]] = []
    for index in range(64):
        words = tuple(
            _read_u32(image, address + index * entry_size + word * 4)
            for word in range(entry_size // 4)
        )
        if words[:2] == terminator:
            return rows
        rows.append(words)
    raise ValueError(f"unterminated table at 0x{address:08x}")


def read_media_values(exe: Path, zh_hans_res: Path) -> list[tuple[str, int, int, str]]:
    strings = load_string_resources(zh_hans_res, None)
    image = PEImage(exe)
    paper_sizes = _read_table(
        image,
        PAPER_SIZE_TABLE,
        PAPER_SIZE_ENTRY_SIZE,
        (0x15, 0x00),
    )
    media_types = _read_table(
        image,
        MEDIA_TYPE_TABLE,
        MEDIA_TYPE_ENTRY_SIZE,
        (0x00, 0x17),
    )
    rows = [
        ("paper_size", value, string_id, strings[string_id])
        for value, _control_id, string_id, *_rest in paper_sizes
    ]
    rows.extend(
        ("media_type", value, string_id, strings[string_id])
        for _category, value, _control_id, string_id, *_rest in media_types
    )
    # FUN_00405c10 selects weight combo index `value - 10`; the first seven
    # RT_STRING entries in that control are the labels below.
    rows.extend(
        ("paper_weight", value, string_id, strings[string_id])
        for value, string_id in zip(range(10, 17), range(145, 138, -1))
    )
    normalized = [
        (
            kind,
            value,
            resource_id,
            LABEL_NORMALIZATIONS.get(label, label),
        )
        for kind, value, resource_id, label in rows
    ]
    order = {"paper_size": 0, "media_type": 1, "paper_weight": 2}
    return sorted(normalized, key=lambda row: (order[row[0]], row[1]))


def format_tsv(rows: list[tuple[str, int, int, str]]) -> str:
    lines = ["kind\tvalue\tresource_id\tzh_hans"]
    for kind, value, resource_id, label in rows:
        lines.append(
            f"{kind}\t{value}\t{resource_id}\t"
            f"{label.replace(chr(9), ' ').replace(chr(10), ' ')}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=Path,
        default=root / "Kyocera" / "ClientTool" / "KMUTLCFG.exe",
    )
    parser.add_argument(
        "--zh-hans-res",
        type=Path,
        default=(
            root
            / "Kyocera"
            / "ClientTool"
            / "LANG"
            / "zh-Hans"
            / "KMUTLCFGRes.dll"
        ),
    )
    args = parser.parse_args()
    for key, path in (("exe", args.exe), ("zh_hans", args.zh_hans_res)):
        actual = _sha256(path)
        if actual != EXPECTED_HASHES[key]:
            raise SystemExit(
                f"{path}: SHA-256 {actual} does not match the supported "
                "ClientTool 1.4.11.2 build"
            )
    sys.stdout.write(format_tsv(read_media_values(args.exe, args.zh_hans_res)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
