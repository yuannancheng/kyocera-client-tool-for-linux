#!/usr/bin/env python3
"""Extract the KMUTLCFG configuration model-offset table.

``FUN_0040e820`` receives one configuration value at a time, maps its OID to a
0-based item index, and stores the value in the application model.  This tool
parses the Ghidra pseudocode for that function and emits one row per item:

    item_id  oid  primary_offset  extra_offsets  status

The offsets are addresses relative to the model base.  A few items are arrays
or compound records and therefore have more than one offset; ``primary_offset``
is the first offset observed in the function and ``extra_offsets`` lists the
rest.  The Ghidra export is not shipped in the repository, so this tool requires
the local ``analysis/decompiled`` tree produced by
``tools/ghidra_scripts/DecompileProgram.java``.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_SOURCE = (
    ROOT
    / "analysis"
    / "decompiled"
    / "KMUTLCFG"
    / "c"
    / "0040e820_FUN_0040e820.c"
)
OID_TABLE = (
    ROOT
    / "docs"
    / "reverse-engineering"
    / "data"
    / "clienttool-config-oids.tsv"
)

# Helper functions called from FUN_0040e820 that write a fixed model field.
HELPER_OFFSETS = {
    "FUN_0040d600": 0x40FC,
    "FUN_0040d640": 0x4200,
    "FUN_0040d680": 0x40E8,
    "FUN_0040da30": 0x3000,
    "FUN_0040da70": 0x3C5C,
    "FUN_0040dab0": 0x3C90,
    "FUN_0040e420": 0x3028,
    "FUN_0040e450": 0x312C,
    "FUN_0040e480": 0x3230,
    "FUN_0040e4b0": 0x3334,
    "FUN_0040e500": 0x3438,
    "FUN_0040e550": 0x353C,
    "FUN_0040e5a0": 0x3640,
    "FUN_0040e5f0": 0x3744,
    "FUN_0040e640": 0x3848,
    "FUN_0040e690": 0x394C,
    "FUN_0040e6e0": 0x3A50,
    "FUN_0040e730": 0x3B54,
    "FUN_0040e760": 0x3DCC,
    "FUN_0040e790": 0x3ED0,
    "FUN_0040e7c0": 0x3FE0,
    "FUN_0040e7f0": 0x4308,
    "FUN_00410590": 0x444C,
    "FUN_004105c0": 0x4550,
    "FUN_004105f0": 0x4654,
    "FUN_00410620": 0x4758,
    "FUN_00410650": 0x486C,
    "FUN_00410680": 0x4970,
    "FUN_004106b0": 0x4A74,
    "FUN_004106e0": 0x4B78,
    "FUN_00410710": 0x4C7C,
}

# ``case 0x46`` and ``case 0x4a`` share one block; the parser sees the last
# label and assigns both offsets to it, so both items are set explicitly.
SHARED_CASE_OFFSETS = {
    0x46: [0x4D84],
    0x49: [0x4F90, 0x4F94, 0x4F98, 0x4F9C, 0x4FA0, 0x4FA4],
    0x4A: [0x4FA8],
    0x4D: [0x51B4, 0x51B8, 0x51BC, 0x51C0, 0x51C4, 0x51C8],
}


def parse_cases(source: Path) -> dict[int, list[int]]:
    text = source.read_text(encoding="utf-8")
    case: int | None = None
    offsets: dict[int, list[int]] = {}
    for line in text.splitlines():
        match = re.match(r"\s*case (0x[0-9a-f]+|\d+):", line)
        if match:
            case = int(match.group(1), 0)
            offsets.setdefault(case, [])
            continue
        if case is None:
            continue
        for value in re.findall(r"param_1 \+ (0x[0-9a-f]+|\d+)", line):
            offset = int(value, 0)
            if offset not in offsets[case]:
                offsets[case].append(offset)
        for helper, offset in HELPER_OFFSETS.items():
            if helper in line and offset not in offsets[case]:
                offsets[case].append(offset)
    for case, values in SHARED_CASE_OFFSETS.items():
        offsets[case] = list(values)
    return offsets


def read_oids(path: Path) -> list[tuple[int, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [(int(row["item_id"]), row["oid"]) for row in rows]


def build_rows(source: Path, oid_table: Path) -> list[dict[str, str]]:
    offsets = parse_cases(source)
    rows = []
    for index, (item_id, oid) in enumerate(read_oids(oid_table)):
        values = offsets.get(index, [])
        primary = f"0x{values[0]:04x}" if values else ""
        extra = ";".join(f"0x{value:04x}" for value in values[1:])
        rows.append(
            {
                "item_id": str(item_id),
                "oid": oid,
                "primary_offset": primary,
                "extra_offsets": extra,
                "status": "mapped" if values else "unresolved",
            }
        )
    return rows


def format_tsv(rows: list[dict[str, str]]) -> str:
    columns = ("item_id", "oid", "primary_offset", "extra_offsets", "status")
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join(row[column] for column in columns))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=MODEL_SOURCE)
    parser.add_argument("--oid-table", type=Path, default=OID_TABLE)
    args = parser.parse_args(argv)
    if not args.source.exists():
        raise SystemExit(
            f"{args.source} is missing; run the Ghidra decompile export first"
        )
    rows = build_rows(args.source, args.oid_table)
    sys.stdout.write(format_tsv(rows))
    unresolved = sum(1 for row in rows if row["status"] != "mapped")
    print(f"mapped {len(rows) - unresolved}/{len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
