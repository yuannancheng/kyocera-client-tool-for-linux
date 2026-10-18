#!/usr/bin/env python3
"""Inventory KMUTLCFG UI control resources without publishing vendor text.

The configuration utility keeps its localized UI text in
``LANG/<locale>/KMUTLCFGRes.dll`` (RT_STRING resources) and its control
binding tables in ``KMUTLCFG.exe``:

* ``0x00496f20``: pairs ``(string_id, control_id)`` for static labels;
* ``0x00497048``: pairs ``(control_id, string_id)`` for combo-box options.

The output is a read-only TSV containing control IDs, resource IDs and text
presence/length only.  Localized strings, captions and combo-box values are
not written to the public data set.  It does not map controls to device OIDs;
that requires tracing each control's model offset and is intentionally kept
separate.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clienttool_oids import PEImage  # noqa: E402


EXPECTED_HASHES = {
    "exe": "63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea",
    "res": "fa8590ce495a1040ddf9dd1239e642021230396f8a52ab50f276b07b0fdfe41c",
}

LABEL_TABLE_VA = 0x00496F20
COMBO_TABLE_VA = 0x00497048
ENGLISH_LCID = 1033


@dataclass(frozen=True)
class UiEntry:
    table: str
    control_id: int | None
    kind: str
    option_index: int | None
    string_id: int
    text_present: bool
    text_length: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_string_resources(path: Path, language: int = ENGLISH_LCID) -> dict[int, str]:
    """Return ``{string_id: text}`` from a PE RT_STRING resource table."""
    image = PEImage(path)
    sections = [section for section in image.sections if section.name == ".rsrc"]
    if not sections:
        raise ValueError(f"{path}: no .rsrc section")
    rsrc_offset = sections[0].raw_pointer

    def directory_entry(relative: int) -> tuple[int, int]:
        return struct.unpack_from("<II", image.data, rsrc_offset + relative)

    def resource_name(relative: int) -> str:
        offset = rsrc_offset + relative
        length = struct.unpack_from("<H", image.data, offset)[0]
        return image.data[offset + 2 : offset + 2 + length * 2].decode(
            "utf-16le", "replace"
        )

    def walk(relative: int, prefix: tuple = ()):
        _, _, _, _, named_count, id_count = struct.unpack_from(
            "<IIHHHH", image.data, rsrc_offset + relative
        )
        for index in range(named_count + id_count):
            entry = relative + 16 + index * 8
            name_field, data_field = directory_entry(entry)
            if name_field & 0x80000000:
                name = resource_name(name_field & 0x7FFFFFFF)
            else:
                name = name_field
            if data_field & 0x80000000:
                yield from walk(data_field & 0x7FFFFFFF, prefix + (name,))
            else:
                yield prefix + (name,), data_field & 0x7FFFFFFF

    strings: dict[int, str] = {}
    for path_parts, data_relative in walk(0):
        # path_parts = (RT_STRING=6, block_id, language)
        if len(path_parts) != 3 or path_parts[0] != 6:
            continue
        if language is not None and path_parts[2] != language:
            continue
        block_id = path_parts[1]
        data_offset = rsrc_offset + data_relative
        rva, size = struct.unpack_from("<II", image.data, data_offset)
        file_offset = image.file_offset(image.image_base + rva)
        block = image.data[file_offset : file_offset + size]
        position = 0
        for index in range(16):
            if position + 2 > len(block):
                break
            length = struct.unpack_from("<H", block, position)[0]
            position += 2
            text = block[position : position + length * 2].decode(
                "utf-16le", "replace"
            )
            position += length * 2
            # RT_STRING block N stores IDs (N-1)*16 ... (N-1)*16+15.
            string_id = (block_id - 1) * 16 + index
            if text:
                strings[string_id] = text
    return strings


def _read_pairs(image: PEImage, va: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for index in range(512):
        offset = image.file_offset(va + index * 8)
        if offset is None:
            raise ValueError(f"unmapped table address 0x{va + index * 8:08x}")
        first, second = struct.unpack_from("<II", image.data, offset)
        if first == 0 and second == 0:
            break
        pairs.append((first, second))
    return pairs


def read_ui_entries(exe_path: Path, res_path: Path) -> list[UiEntry]:
    strings = load_string_resources(res_path)
    image = PEImage(exe_path)
    entries: list[UiEntry] = []

    for string_id, control_id in _read_pairs(image, LABEL_TABLE_VA):
        text = strings.get(string_id, "").rstrip()
        if control_id == 0xFFFFFFFF:
            entries.append(
                UiEntry(
                    "label",
                    None,
                    "section",
                    None,
                    string_id,
                    bool(text),
                    len(text),
                )
            )
        else:
            entries.append(
                UiEntry(
                    "label",
                    control_id,
                    "label",
                    None,
                    string_id,
                    bool(text),
                    len(text),
                )
            )

    option_counts: dict[int, int] = {}
    for control_id, string_id in _read_pairs(image, COMBO_TABLE_VA):
        option_index = option_counts.get(control_id, 0)
        option_counts[control_id] = option_index + 1
        entries.append(
            UiEntry(
                "combo",
                control_id,
                "combo_option",
                option_index,
                string_id,
                bool(strings.get(string_id, "").rstrip()),
                len(strings.get(string_id, "").rstrip()),
            )
        )
    return entries


def format_tsv(entries: list[UiEntry]) -> str:
    lines = [
        "table\tcontrol_id\tkind\toption_index\tstring_id\ttext_present\ttext_length"
    ]
    for entry in entries:
        control = (
            f"0x{entry.control_id:04x}" if entry.control_id is not None else ""
        )
        option = "" if entry.option_index is None else str(entry.option_index)
        lines.append(
            f"{entry.table}\t{control}\t{entry.kind}\t{option}\t"
            f"{entry.string_id}\t{int(entry.text_present)}\t{entry.text_length}"
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
        "--res-dll",
        type=Path,
        default=(
            root
            / "Kyocera"
            / "ClientTool"
            / "LANG"
            / "en"
            / "KMUTLCFGRes.dll"
        ),
    )
    args = parser.parse_args()
    for key, path in (("exe", args.exe), ("res", args.res_dll)):
        actual = _sha256(path)
        if actual != EXPECTED_HASHES[key]:
            raise SystemExit(
                f"{path}: SHA-256 {actual} does not match the supported "
                f"ClientTool 1.4.11.2 build"
            )
    sys.stdout.write(format_tsv(read_ui_entries(args.exe, args.res_dll)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
