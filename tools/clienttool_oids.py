#!/usr/bin/env python3
"""Extract protocol object tables from the packaged KYOCERA Client Tool.

The extractor is read-only.  It only parses the PE section table and two
static tables that are embedded in KMUTLCFG.exe and KMUTLPRE.exe:

* KMUTLCFG.exe: 147-row configuration table used for SNMP GET/SET and for
  USB PJL KGETOBJ/KSETOBJ requests.
* KMUTLPRE.exe: preset object table and the scan-preset item list used by
  the preset utility.

The addresses and expected hashes belong to ClientTool 1.4.11.2 (package
dated 2022-11-09).  A different build fails closed instead of producing a
plausible but wrong table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


EXPECTED_HASHES = {
    "config": "63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea",
    "preset": "4635fb4f85e2204e15dd937cfc08411de47fc7a4a857ec78beb8a2a40e3d499e",
}

CONFIG_TABLE_VA = 0x00498244
CONFIG_TABLE_ROWS = 147
CONFIG_TABLE_STRIDE = 12

PRESET_TABLE_VA = 0x005048D8
PRESET_TABLE_STRIDE = 16
PRESET_LIST_VA = 0x004FFD90
PRESET_LIST_TERMINATOR = 0x39

# Known value-type codes in the KMUTLCFG table.
TYPE_NAMES = {
    0: "integer",
    3: "ipv4",
    5: "string",
    6: "mac",
}


@dataclass(frozen=True)
class Section:
    name: str
    virtual_address: int
    virtual_size: int
    raw_pointer: int
    raw_size: int


class PEImage:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        if self.data[:2] != b"MZ":
            raise ValueError(f"{path}: not an MZ/PE image")
        pe_offset = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[pe_offset : pe_offset + 4] != b"PE\0\0":
            raise ValueError(f"{path}: missing PE signature")
        coff = pe_offset + 4
        section_count = struct.unpack_from("<H", self.data, coff + 2)[0]
        optional_size = struct.unpack_from("<H", self.data, coff + 16)[0]
        optional = coff + 20
        magic = struct.unpack_from("<H", self.data, optional)[0]
        if magic != 0x10B:
            raise ValueError(f"{path}: expected PE32 image, magic=0x{magic:04x}")
        self.image_base = struct.unpack_from("<I", self.data, optional + 28)[0]
        section_table = coff + 20 + optional_size
        self.sections: list[Section] = []
        for index in range(section_count):
            offset = section_table + index * 40
            name = self.data[offset : offset + 8].rstrip(b"\0").decode(
                "ascii", "replace"
            )
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
                "<IIII", self.data, offset + 8
            )
            self.sections.append(
                Section(name, virtual_address, virtual_size, raw_pointer, raw_size)
            )

    def file_offset(self, va: int) -> int | None:
        for section in self.sections:
            start = self.image_base + section.virtual_address
            if start <= va < start + section.virtual_size:
                return section.raw_pointer + (va - start)
        return None

    def c_string(self, va: int) -> str | None:
        offset = self.file_offset(va)
        if offset is None:
            return None
        end = self.data.find(b"\0", offset)
        if end < 0:
            return None
        return self.data[offset:end].decode("latin1", "replace")

    def u32(self, va: int) -> int:
        offset = self.file_offset(va)
        if offset is None:
            raise ValueError(f"unmapped VA 0x{va:08x}")
        return struct.unpack_from("<I", self.data, offset)[0]


def pjl_object(oid: str, preset: bool = False) -> str:
    """ClientTool's PJL object spelling for a given numeric OID."""
    if preset or oid.startswith("1.3.6"):
        return f"#{oid}"
    return f"1.{oid}"


def read_config_rows(image: PEImage) -> list[dict]:
    rows = []
    for index in range(CONFIG_TABLE_ROWS):
        va = CONFIG_TABLE_VA + index * CONFIG_TABLE_STRIDE
        oid_ptr, type_code, item_id = struct.unpack_from(
            "<III", image.data, image.file_offset(va)
        )
        oid = image.c_string(oid_ptr)
        if oid is None:
            raise ValueError(f"row {index}: OID pointer 0x{oid_ptr:08x} is unmapped")
        rows.append(
            {
                "index": index,
                "item_id": item_id,
                "oid": oid,
                "type_code": type_code,
                "type": TYPE_NAMES.get(type_code, f"unknown({type_code})"),
                "pjl_object": pjl_object(oid),
            }
        )
    return rows


def read_preset_rows(image: PEImage) -> list[dict]:
    rows = []
    for index in range(256):
        va = PRESET_TABLE_VA + index * PRESET_TABLE_STRIDE
        item_id, fmt_ptr, flags, tag = struct.unpack_from(
            "<IIII", image.data, image.file_offset(va)
        )
        if fmt_ptr == 0:
            break
        fmt = image.c_string(fmt_ptr)
        if fmt is None:
            raise ValueError(f"preset row {index}: format pointer is unmapped")
        rows.append(
            {
                "index": index,
                "item_id": item_id,
                "oid_format": fmt,
                "flags": flags,
                "tag": tag,
                "pjl_object_format": (
                    f"#{fmt}" if fmt.startswith("1.3.6") else ""
                ),
            }
        )
    return rows


def read_preset_list(image: PEImage) -> list[int]:
    values = []
    for index in range(256):
        value = image.u32(PRESET_LIST_VA + index * 4)
        if value == PRESET_LIST_TERMINATOR:
            break
        values.append(value)
    return values


def print_tsv(rows: list[dict]) -> None:
    if not rows:
        return
    print("\t".join(rows[0].keys()))
    for row in rows:
        print("\t".join(str(row[key]) for key in rows[0]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "binary",
        choices=("config", "preset"),
        help="which packaged utility to inspect",
    )
    parser.add_argument(
        "--clienttool-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "Kyocera" / "ClientTool",
        help="directory containing KMUTLCFG.exe / KMUTLPRE.exe",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of TSV")
    args = parser.parse_args()

    name = "KMUTLCFG.exe" if args.binary == "config" else "KMUTLPRE.exe"
    path = args.clienttool_dir / name
    if not path.is_file():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2

    image = PEImage(path)
    digest = hashlib.sha256(image.data).hexdigest()
    if digest != EXPECTED_HASHES[args.binary]:
        print(
            f"error: {path} SHA-256 {digest} does not match the analyzed build "
            f"{EXPECTED_HASHES[args.binary]}; refusing to use build-specific offsets",
            file=sys.stderr,
        )
        return 3
    if args.binary == "config":
        rows = read_config_rows(image)
    else:
        rows = read_preset_rows(image)

    if args.json:
        payload = {
            "source": str(path),
            "sha256": digest,
            "rows": rows,
        }
        if args.binary == "preset":
            payload["scan_preset_item_list"] = read_preset_list(image)
        json.dump(payload, sys.stdout, indent=2)
        print()
    else:
        print_tsv(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
