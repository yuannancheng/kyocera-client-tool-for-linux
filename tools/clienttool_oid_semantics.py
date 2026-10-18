#!/usr/bin/env python3
"""Validate and merge curated ClientTool OID semantics.

The all-OID inventory keeps vendor symbol names separate from analyst-confirmed
semantics.  This tool joins the curated semantics table to that inventory,
reports how many formerly unnamed OIDs are now covered, and can emit the merged
TSV used by the master inventory.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "reverse-engineering" / "data"
DEFAULT_SEMANTICS = DATA / "clienttool-oid-semantics.tsv"
DEFAULT_INVENTORY = DATA / "clienttool-all-oids.tsv"

REQUIRED_COLUMNS = (
    "oid",
    "semantic_name",
    "group",
    "direction",
    "snmp_type",
    "value_encoding",
    "values",
    "confidence",
    "evidence",
    "device_2026_10_18",
    "notes",
)
MERGE_COLUMNS = (
    "semantic_name",
    "semantic_group",
    "semantic_direction",
    "semantic_type",
    "semantic_values",
    "semantic_confidence",
)


def _read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or ()), list(reader)


def load_semantics(path: Path = DEFAULT_SEMANTICS) -> list[dict[str, str]]:
    columns, rows = _read_tsv(path)
    if tuple(columns) != REQUIRED_COLUMNS:
        raise ValueError(
            f"{path}: expected columns {REQUIRED_COLUMNS}, got {tuple(columns)}"
        )
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        oid = row["oid"].strip()
        if not oid.startswith("1.3.6.1."):
            raise ValueError(f"{path}:{line}: invalid OID {oid!r}")
        if oid in seen:
            raise ValueError(f"{path}:{line}: duplicate OID {oid}")
        seen.add(oid)
        if not row["semantic_name"].strip():
            raise ValueError(f"{path}:{line}: empty semantic_name")
        if not row["evidence"].strip():
            raise ValueError(f"{path}:{line}: empty evidence")
    return rows


def load_inventory(path: Path = DEFAULT_INVENTORY) -> list[dict[str, str]]:
    _, rows = _read_tsv(path)
    return rows


def coverage(
    inventory: list[dict[str, str]],
    semantics: list[dict[str, str]],
) -> dict[str, object]:
    by_oid = {row["oid"]: row for row in inventory}
    device_rows = [
        row for row in inventory if row.get("oid_role") != "library-constant"
    ]
    unnamed = {
        row["oid"]
        for row in device_rows
        if not row.get("symbols") and not row.get("prefix_symbols")
    }
    covered = set(by_oid) & {row["oid"] for row in semantics}
    missing = sorted({row["oid"] for row in semantics} - set(by_oid))
    exact_conflicts = sorted(
        oid
        for oid in covered
        if by_oid[oid].get("symbols")
    )
    prefix_overrides = sorted(
        oid
        for oid in covered
        if not by_oid[oid].get("symbols") and by_oid[oid].get("prefix_symbols")
    )
    groups: dict[str, int] = {}
    for row in semantics:
        groups[row["group"]] = groups.get(row["group"], 0) + 1
    return {
        "inventory_oids": len(inventory),
        "library_constants": len(inventory) - len(device_rows),
        "device_oids": len(device_rows),
        "unnamed": len(unnamed),
        "semantics_rows": len(semantics),
        "covered": len(covered & unnamed),
        "missing_from_inventory": missing,
        "conflicting_with_vendor_name": exact_conflicts,
        "prefix_symbol_overrides": prefix_overrides,
        "remaining": len(unnamed - covered),
        "remaining_oids": sorted(unnamed - covered),
        "groups": dict(sorted(groups.items())),
    }


def merge_rows(
    inventory: list[dict[str, str]],
    semantics: list[dict[str, str]],
) -> list[dict[str, str]]:
    by_oid = {row["oid"]: row for row in semantics}
    merged: list[dict[str, str]] = []
    for row in inventory:
        item = dict(row)
        semantic = by_oid.get(row["oid"], {})
        item["semantic_name"] = semantic.get("semantic_name", "")
        item["semantic_group"] = semantic.get("group", "")
        item["semantic_direction"] = semantic.get("direction", "")
        item["semantic_type"] = semantic.get("snmp_type", "")
        item["semantic_values"] = semantic.get("values", "")
        item["semantic_confidence"] = semantic.get("confidence", "")
        merged.append(item)
    return merged


def format_tsv(rows: list[dict[str, str]], columns: list[str]) -> str:
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append(
            "\t".join(row.get(column, "").replace("\t", " ") for column in columns)
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantics", type=Path, default=DEFAULT_SEMANTICS)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument(
        "--merge-tsv",
        action="store_true",
        help="write the inventory with semantic_* columns instead of a summary",
    )
    parser.add_argument("--json", action="store_true", help="JSON coverage summary")
    args = parser.parse_args(argv)

    semantics = load_semantics(args.semantics)
    inventory = load_inventory(args.inventory)
    summary = coverage(inventory, semantics)

    if args.merge_tsv:
        columns = list(inventory[0].keys()) + list(MERGE_COLUMNS)
        sys.stdout.write(format_tsv(merge_rows(inventory, semantics), columns))
        return 0

    if args.json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"inventory OIDs: {summary['inventory_oids']}")
    print(f"library constants: {summary['library_constants']}")
    print(f"device OIDs: {summary['device_oids']}")
    print(f"unnamed OIDs: {summary['unnamed']}")
    print(f"semantic rows: {summary['semantics_rows']}")
    print(f"newly covered: {summary['covered']}")
    print(f"remaining unnamed: {summary['remaining']}")
    print("groups: " + ", ".join(
        f"{name}={count}" for name, count in summary["groups"].items()
    ))
    if summary["missing_from_inventory"]:
        print("missing from inventory: " + ", ".join(
            summary["missing_from_inventory"]
        ))
    if summary["conflicting_with_vendor_name"]:
        print("conflicts with vendor name: " + ", ".join(
            summary["conflicting_with_vendor_name"]
        ))
    if summary["prefix_symbol_overrides"]:
        print("curated rows over inherited prefix symbols: " + ", ".join(
            summary["prefix_symbol_overrides"]
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
