#!/usr/bin/env python3
"""Expand ``JobSnmpOid.xml`` into absolute job-subtree OIDs.

``Kyocera/ClientTool/WFH/remotefax/addins/Device/Device.DeviceJobs/conf/
JobSnmpOid.xml`` is a tree, not a prefix table:

* ``rootJob`` carries the absolute root ``1.3.6.1.4.1.1347.47``;
* most children carry one relative OID component, which is appended to the
  parent's absolute OID;
* ``additionalOIDS`` entries carry their own absolute OIDs.

This tool expands every element with an ``oid`` attribute into an absolute
OID and emits ``symbol``, ``oid``, ``path`` and ``oid_kind`` in document
order.  It fails closed on a relative OID without a parent, a non-numeric
relative component, or a duplicate absolute OID.  The target file is read
only and is verified against the supported ClientTool build.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XML = (
    ROOT
    / "Kyocera"
    / "ClientTool"
    / "WFH"
    / "remotefax"
    / "addins"
    / "Device"
    / "Device.DeviceJobs"
    / "conf"
    / "JobSnmpOid.xml"
)
EXPECTED_SHA256 = (
    "2e5f665929ed9e8cf5efe1eba64524ee5902dcbfe177160e8bc1305306fa1fed"
)
COLUMNS = ("symbol", "oid", "path", "oid_kind")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _symbol(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _is_absolute(oid: str) -> bool:
    return oid.lstrip(".").startswith("1.3.6")


def _normalize_absolute(oid: str) -> str:
    return oid.strip().lstrip(".")


def _is_numeric_oid(oid: str) -> bool:
    return bool(oid) and all(part.isdigit() for part in oid.split("."))


def expand_job_oids(path: Path) -> list[dict[str, str]]:
    tree = ET.parse(path)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def walk(element: ET.Element, parent: str | None, path_parts: tuple[str, ...]):
        for child in element:
            symbol = _symbol(child)
            raw = (child.get("oid") or "").strip()
            child_path = path_parts + (symbol,)
            if not raw:
                walk(child, parent, child_path)
                continue
            if _is_absolute(raw):
                absolute = _normalize_absolute(raw)
                kind = "absolute"
            else:
                if not parent:
                    raise ValueError(
                        f"{'/'.join(child_path)}: relative oid without parent"
                    )
                if not _is_numeric_oid(raw):
                    raise ValueError(
                        f"{'/'.join(child_path)}: non-numeric relative oid {raw!r}"
                    )
                absolute = f"{parent}.{raw}"
                kind = "relative"
            if absolute in seen:
                raise ValueError(f"duplicate absolute oid {absolute}")
            seen.add(absolute)
            rows.append(
                {
                    "symbol": symbol,
                    "oid": absolute,
                    "path": "/".join(child_path),
                    "oid_kind": kind,
                }
            )
            walk(child, absolute, child_path)

    walk(tree.getroot(), None, ())
    return rows


def format_tsv(rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in rows:
        lines.append("\t".join(row[column] for column in COLUMNS))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    args = parser.parse_args(argv)
    actual = _sha256(args.xml)
    if actual != EXPECTED_SHA256:
        raise SystemExit(
            f"{args.xml}: SHA-256 {actual} does not match the supported "
            "ClientTool 1.4.11.2 package"
        )
    sys.stdout.write(format_tsv(expand_job_oids(args.xml)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
