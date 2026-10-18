#!/usr/bin/env python3
"""Match the 147 ClientTool configuration OIDs to vendor symbol names.

The Client Tool package ships two ``snmp-oid.xml`` files:

* ``WIFI/wifisetup/def/dev/snmp-oid.xml``
* ``WFH/remotefax/system/Device.Base/def/dev/snmp-oid.xml``

Both map vendor OID prefixes to symbolic names.  This tool merges them,
performs a longest-prefix match against the 147-row object table, and emits a
full vendor-OID index.  The merged table still names 127 objects, including
the complete ``45.*`` fax group; the other 20 objects are not described by
either file.

The output is read-only.  ``--python-output`` also emits a small module used by
``kyocera_monitor.config`` so the CLI can show vendor names without shipping
the XML or depending on the repository layout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OID_TABLE = (
    ROOT
    / "docs"
    / "reverse-engineering"
    / "data"
    / "clienttool-config-oids.tsv"
)
WIFI_XML = (
    ROOT
    / "Kyocera"
    / "ClientTool"
    / "WIFI"
    / "wifisetup"
    / "def"
    / "dev"
    / "snmp-oid.xml"
)
REMOTEFAX_XML = (
    ROOT
    / "Kyocera"
    / "ClientTool"
    / "WFH"
    / "remotefax"
    / "system"
    / "Device.Base"
    / "def"
    / "dev"
    / "snmp-oid.xml"
)
DEFAULT_XMLS = (WIFI_XML, REMOTEFAX_XML)
EXPECTED_XML_SHA256 = {
    WIFI_XML: "cc62170944f7d2251ebc262f3d0a81c3a991c9d31d88da383928620408bdad4a",
    REMOTEFAX_XML: "cb745cc3f48bdb1babfe1307664f40dff8785e63999447c361fe6fe3da747035",
}
INDEX_COLUMNS = ("oid", "symbol", "source")
KYOCERA_ROOT = "1.3.6.1.4.1.1347."


@dataclass(frozen=True)
class VendorName:
    item_id: int
    oid: str
    vendor_name: str
    vendor_base_oid: str
    match: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_vendor_oids(path: Path) -> dict[str, list[str]]:
    """Return ``{oid: [symbol, ...]}`` from the ClientTool OID XML."""
    names: dict[str, list[str]] = {}
    for element in ET.parse(path).getroot().iter():
        oid = element.get("oid")
        if not oid:
            continue
        symbol = element.tag.rsplit("}", 1)[-1]
        names.setdefault(oid, [])
        if symbol not in names[oid]:
            names[oid].append(symbol)
    return names


def merge_vendor_oids(paths: tuple[Path, ...]) -> dict[str, list[str]]:
    """Merge several ``snmp-oid.xml`` files without dropping aliases."""
    merged: dict[str, list[str]] = {}
    for path in paths:
        for oid, names in read_vendor_oids(path).items():
            merged.setdefault(oid, [])
            for name in names:
                if name not in merged[oid]:
                    merged[oid].append(name)
    return merged


def build_vendor_index(paths: tuple[Path, ...]) -> list[dict[str, str]]:
    """Return one row per (oid, symbol, source) across the given XML files."""
    rows: list[dict[str, str]] = []
    for path in paths:
        source = path.relative_to(ROOT).as_posix()
        for oid, names in read_vendor_oids(path).items():
            for name in names:
                rows.append({"oid": oid, "symbol": name, "source": source})
    rows.sort(key=lambda row: (row["oid"], row["symbol"], row["source"]))
    return rows


def absolute_oid(oid: str) -> str:
    return oid if oid.startswith("1.3.6") else KYOCERA_ROOT + oid


def match_oid(oid: str, vendor_oids: dict[str, list[str]]) -> tuple[list[str], str, str]:
    """Return names, matched base OID and match kind for one config OID."""
    absolute = absolute_oid(oid)
    candidates = [
        base
        for base in vendor_oids
        if absolute == base or absolute.startswith(base + ".")
    ]
    if not candidates:
        return [], "", "none"
    base = max(candidates, key=len)
    names = sorted(vendor_oids[base])
    return names, base, "exact" if base == absolute else "table"


def build_rows(oid_table: Path, vendor_oids: dict[str, list[str]]) -> list[VendorName]:
    with oid_table.open(newline="", encoding="utf-8") as handle:
        config_rows = list(csv.DictReader(handle, delimiter="\t"))
    rows = []
    for row in config_rows:
        names, base, kind = match_oid(row["oid"], vendor_oids)
        rows.append(
            VendorName(
                item_id=int(row["item_id"]),
                oid=row["oid"],
                vendor_name="|".join(names),
                vendor_base_oid=base,
                match=kind,
            )
        )
    return rows


def format_tsv(rows: list[VendorName]) -> str:
    lines = ["item_id\toid\tvendor_name\tvendor_base_oid\tmatch"]
    for row in rows:
        lines.append(
            f"{row.item_id}\t{row.oid}\t{row.vendor_name}\t"
            f"{row.vendor_base_oid}\t{row.match}"
        )
    return "\n".join(lines) + "\n"


def format_python(rows: list[VendorName]) -> str:
    lines = [
        '"""Generated by tools/clienttool_config_names.py; do not edit."""',
        "",
        "VENDOR_NAMES: dict[str, str] = {",
    ]
    for row in rows:
        if row.vendor_name:
            lines.append(f'    {row.oid!r}: {row.vendor_name!r},')
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def format_vendor_index(rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(INDEX_COLUMNS)]
    for row in rows:
        lines.append("\t".join(row[column] for column in INDEX_COLUMNS))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xml",
        type=Path,
        action="append",
        help="snmp-oid.xml to merge; repeatable; defaults to both ClientTool files",
    )
    parser.add_argument("--oid-table", type=Path, default=OID_TABLE)
    parser.add_argument(
        "--python-output",
        type=Path,
        help="also write the VENDOR_NAMES module to this path",
    )
    parser.add_argument(
        "--index-output",
        type=Path,
        help="also write the merged oid/symbol/source index to this path",
    )
    args = parser.parse_args()
    xmls = tuple(args.xml) if args.xml else DEFAULT_XMLS
    for path in xmls:
        expected = EXPECTED_XML_SHA256.get(path)
        if expected is None:
            raise SystemExit(f"{path}: unsupported snmp-oid.xml")
        actual = _sha256(path)
        if actual != expected:
            raise SystemExit(
                f"{path}: SHA-256 {actual} does not match the supported "
                "ClientTool 1.4.11.2 package"
            )
    rows = build_rows(args.oid_table, merge_vendor_oids(xmls))
    if args.python_output:
        args.python_output.write_text(format_python(rows), encoding="utf-8")
    if args.index_output:
        args.index_output.write_text(
            format_vendor_index(build_vendor_index(xmls)), encoding="utf-8"
        )
    sys.stdout.write(format_tsv(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
