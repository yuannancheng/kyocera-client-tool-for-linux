#!/usr/bin/env python3
"""Inventory dialog-control metadata without publishing vendor captions.

``KMUTLCFG.exe`` keeps its dialog templates in the PE resource directory
(``RT_DIALOG``).  Each template carries the dialog ordinal, control IDs,
window classes, coordinates and localized text.  The public TSV records only
the structural metadata and whether text is present; it does not reproduce
vendor captions or control labels.  The extractor is read-only.

Supported: PE32 ``DLGTEMPLATE`` and ``DLGTEMPLATEEX`` resources from
ClientTool 1.4.11.2.  A different build fails closed.
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


EXPECTED_HASH = "63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea"
RT_DIALOG = 5
DS_SETFONT = 0x00000040


@dataclass(frozen=True)
class DialogControl:
    dialog: int
    control_id: int
    window_class: str
    text_present: bool
    text_length: int
    x: int
    y: int
    cx: int
    cy: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resource_entries(image: PEImage):
    """Yield ``(path, rva, size)`` for every leaf resource entry."""
    sections = [section for section in image.sections if section.name == ".rsrc"]
    if not sections:
        raise ValueError(f"{image.path}: no .rsrc section")
    base = sections[0].raw_pointer

    def name(relative: int) -> int | str:
        offset = base + relative
        first = struct.unpack_from("<H", image.data, offset)[0]
        if first & 0x80000000:
            string_offset = base + (first & 0x7FFFFFFF)
            length = struct.unpack_from("<H", image.data, string_offset)[0]
            return image.data[
                string_offset + 2 : string_offset + 2 + length * 2
            ].decode("utf-16le", "replace")
        return first

    def walk(relative: int, prefix: tuple = ()):
        _, _, _, _, named, ids = struct.unpack_from(
            "<IIHHHH", image.data, base + relative
        )
        for index in range(named + ids):
            entry = base + relative + 16 + index * 8
            name_field, data_field = struct.unpack_from("<II", image.data, entry)
            entry_name = name(name_field & 0x7FFFFFFF) if name_field & 0x80000000 else name_field
            if data_field & 0x80000000:
                yield from walk(data_field & 0x7FFFFFFF, prefix + (entry_name,))
            else:
                data_offset = base + (data_field & 0x7FFFFFFF)
                rva, size = struct.unpack_from("<II", image.data, data_offset)
                yield prefix + (entry_name,), rva, size

    yield from walk(0)


def _read_padded_string(data: bytes, position: int) -> tuple[str, int]:
    """Read one ``sz_*`` header field (empty, ordinal or UTF-16 string)."""
    first = struct.unpack_from("<H", data, position)[0]
    if first == 0:
        return "", position + 2
    if first == 0xFFFF:
        ordinal = struct.unpack_from("<H", data, position + 2)[0]
        return f"#{ordinal}", position + 4
    end = position
    while end + 1 < len(data) and data[end : end + 2] != b"\0\0":
        end += 2
    return data[position : end + 2].decode("utf-16le", "replace").rstrip("\0"), end + 2


def _read_sz(data: bytes, position: int) -> tuple[str, int]:
    """Read a control class/text field (empty, ordinal, or UTF-16 string)."""
    first = struct.unpack_from("<H", data, position)[0]
    if first == 0:
        return "", position + 2
    if first == 0xFFFF:
        ordinal = struct.unpack_from("<H", data, position + 2)[0]
        return f"#{ordinal}", position + 4
    end = position
    while end + 1 < len(data) and data[end : end + 2] != b"\0\0":
        end += 2
    return data[position : end + 2].decode("utf-16le", "replace").rstrip("\0"), end + 2


def _align4(value: int) -> int:
    return (value + 3) & ~3


def parse_dialog(data: bytes, dialog: int) -> tuple[str, list[DialogControl]]:
    # DLGTEMPLATEEX starts with dlgVer=1, signature=0xFFFF.
    extended = struct.unpack_from("<HH", data, 0)[0:2] == (1, 0xFFFF)
    if extended:
        position = 4
        position += 4  # helpID
        position += 4  # exStyle
        style = struct.unpack_from("<I", data, position)[0]
        position += 4
        count = struct.unpack_from("<H", data, position)[0]
        position += 2
        position += 8  # x, y, cx, cy
    else:
        style = struct.unpack_from("<I", data, 0)[0]
        position = 4
        position += 4  # exStyle
        count = struct.unpack_from("<H", data, position)[0]
        position += 2
        position += 8  # x, y, cx, cy

    _, position = _read_padded_string(data, position)  # menu
    _, position = _read_padded_string(data, position)  # windowClass
    caption, position = _read_padded_string(data, position)

    if style & DS_SETFONT:
        if extended:
            position += 2  # pointsize
            position += 2  # weight
            position += 2  # italic, charset
        else:
            position += 2  # pointsize
        _, position = _read_padded_string(data, position)  # typeface

    position = _align4(position)
    controls: list[DialogControl] = []
    for _ in range(count):
        if extended:
            position += 4  # helpID
            position += 4  # exStyle
            position += 4  # style
        else:
            position += 4  # style
            position += 4  # exStyle
        x, y, cx, cy = struct.unpack_from("<hhhh", data, position)
        position += 8
        if extended:
            control_id = struct.unpack_from("<I", data, position)[0]
            position += 4
        else:
            control_id = struct.unpack_from("<H", data, position)[0]
            position += 2
        window_class, position = _read_sz(data, position)
        text, position = _read_sz(data, position)
        extra = struct.unpack_from("<H", data, position)[0]
        position += 2 + extra
        position = _align4(position)
        controls.append(
            DialogControl(
                dialog=dialog,
                control_id=control_id,
                window_class=window_class,
                text_present=bool(text),
                text_length=len(text),
                x=x,
                y=y,
                cx=cx,
                cy=cy,
            )
        )
    return caption, controls


def read_dialogs(path: Path) -> list[DialogControl]:
    image = PEImage(path)
    controls: list[DialogControl] = []
    for resource_path, rva, size in _resource_entries(image):
        if len(resource_path) != 3 or resource_path[0] != RT_DIALOG:
            continue
        dialog = resource_path[1]
        if not isinstance(dialog, int):
            continue
        offset = image.file_offset(image.image_base + rva)
        if offset is None:
            continue
        _, parsed = parse_dialog(image.data[offset : offset + size], dialog)
        controls.extend(parsed)
    return controls


def format_tsv(controls: list[DialogControl]) -> str:
    lines = [
        "dialog\tcontrol_id\tclass\ttext_present\ttext_length\tx\ty\tcx\tcy"
    ]
    for control in sorted(controls, key=lambda item: (item.dialog, item.control_id)):
        lines.append(
            f"0x{control.dialog:04x}\t0x{control.control_id:04x}\t"
            f"{control.window_class}\t{int(control.text_present)}\t"
            f"{control.text_length}\t{control.x}\t{control.y}\t"
            f"{control.cx}\t{control.cy}"
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
    args = parser.parse_args()
    actual = _sha256(args.exe)
    if actual != EXPECTED_HASH:
        raise SystemExit(
            f"{args.exe}: SHA-256 {actual} does not match the supported "
            "ClientTool 1.4.11.2 build"
        )
    sys.stdout.write(format_tsv(read_dialogs(args.exe)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
