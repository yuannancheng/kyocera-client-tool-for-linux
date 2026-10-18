#!/usr/bin/env python3
"""Parse ``FAX/KMSNMP4.INI`` into named SNMP OID rows.

The fax module ships an INI table:

    [00000101]  ; INFO_MODELNAME
    oid=1.3.6.1.4.1.1347.43.5.1.1.1
    size=32
    type=4

Section IDs are numeric request IDs; the comment after ``;`` is the symbolic
name.  A single ``oid=`` line may list several OIDs separated by ``;`` (table
variants sharing one name), so the tool expands those into one row per
``(section, name, oid)``.  The file is read only and verified against the
supported ClientTool build.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INI = ROOT / "Kyocera" / "ClientTool" / "FAX" / "KMSNMP4.INI"
EXPECTED_SHA256 = (
    "c20d172be5dbdb9f2cee81fa3139756328687233d1d0eee2a8d01cfcf935bc6f"
)
COLUMNS = ("section", "name", "oid", "size", "type")
SECTION_RE = re.compile(r"\[([^\]]+)\]\s*(?:;\s*(.*))?$")
OID_RE = re.compile(r"^1\.3\.6(?:\.\d+)+$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_ini(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    section = ""
    name = ""
    oid_value = ""
    size = ""
    oid_type = ""

    def flush() -> None:
        if not section or not oid_value:
            return
        for oid in oid_value.split(";"):
            oid = oid.strip()
            if OID_RE.match(oid):
                rows.append(
                    {
                        "section": section,
                        "name": name,
                        "oid": oid,
                        "size": size,
                        "type": oid_type,
                    }
                )

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        match = SECTION_RE.match(stripped)
        if match:
            flush()
            section = match.group(1).strip()
            name = (match.group(2) or "").strip()
            oid_value = ""
            size = ""
            oid_type = ""
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "oid":
            oid_value = value
        elif key == "size":
            size = value
        elif key == "type":
            oid_type = value
    flush()
    return rows


def format_tsv(rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in rows:
        lines.append("\t".join(row[column] for column in COLUMNS))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ini", type=Path, default=DEFAULT_INI)
    args = parser.parse_args(argv)
    actual = _sha256(args.ini)
    if actual != EXPECTED_SHA256:
        raise SystemExit(
            f"{args.ini}: SHA-256 {actual} does not match the supported "
            "ClientTool 1.4.11.2 package"
        )
    sys.stdout.write(format_tsv(parse_ini(args.ini)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
