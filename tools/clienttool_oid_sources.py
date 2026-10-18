#!/usr/bin/env python3
"""Inventory ClientTool XML files that carry SNMP OID mappings.

The Client Tool package has more than one OID source.  ``snmp-oid.xml`` files
are prefix/symbol tables, ``JobSnmpOid.xml`` is a hierarchical tree whose
children use relative OIDs, and ``Support.xml`` carries a few absolute OIDs
for application/user information.  This tool scans ``Kyocera/ClientTool``
read-only and emits one TSV row per XML file that contains an ``oid``
attribute.

Columns:

    source           path relative to the repository root
    kind             filename-based classification
    oid_elements     number of elements with an oid attribute
    absolute_oids    oids starting with 1.3.6 (or .1.3.6)
    relative_oids    numeric or otherwise relative oids

The classification is descriptive, not proof that a program uses the file.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT / "Kyocera" / "ClientTool"
COLUMNS = (
    "source",
    "kind",
    "oid_elements",
    "absolute_oids",
    "relative_oids",
)


def classify(path: Path) -> str:
    if path.name == "snmp-oid.xml":
        return "prefix-symbol"
    if path.name == "JobSnmpOid.xml":
        return "hierarchical-job"
    if path.name == "Support.xml":
        return "support-info"
    if path.name == "snmp-discovery.xml":
        return "discovery-settings"
    return "other"


def _is_absolute(oid: str) -> bool:
    return oid.lstrip(".").startswith("1.3.6")


def inventory(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(root.rglob("*.xml")):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b'oid="' not in raw:
            continue
        try:
            tree = ET.fromstring(raw)
        except ET.ParseError as error:
            rows.append(
                {
                    "source": path.relative_to(ROOT).as_posix(),
                    "kind": "unparsed",
                    "oid_elements": "0",
                    "absolute_oids": "0",
                    "relative_oids": "0",
                    "error": str(error),
                }
            )
            continue
        oids = [
            element.get("oid", "").strip()
            for element in tree.iter()
            if element.get("oid")
        ]
        absolute = sum(1 for oid in oids if _is_absolute(oid))
        rows.append(
            {
                "source": path.relative_to(ROOT).as_posix(),
                "kind": classify(path),
                "oid_elements": str(len(oids)),
                "absolute_oids": str(absolute),
                "relative_oids": str(len(oids) - absolute),
            }
        )
    return rows


def format_tsv(rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in rows:
        lines.append("\t".join(row[column] for column in COLUMNS))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    sys.stdout.write(format_tsv(inventory(args.root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
