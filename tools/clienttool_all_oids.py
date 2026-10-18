#!/usr/bin/env python3
"""Inventory every dotted OID found anywhere under ``Kyocera/ClientTool``.

The scanner reads every regular file, extracts ASCII and UTF-16LE occurrences
of ``1.3.6.1.*``, and merges the results with the structured name sources:

* the two ``snmp-oid.xml`` prefix tables;
* the expanded ``JobSnmpOid.xml`` tree;
* the two ``Support.xml`` files;
* ``FAX/KMSNMP4.INI`` (``INFO_*`` names).

Output is one row per unique OID with exact symbols, the nearest named
ancestor for instances, curated analyst semantics, 147-object-table relations,
and all source files.  Raw bytes and surrounding vendor text are deliberately
not emitted: the public data set contains protocol identifiers only.
The scan is read only.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clienttool_config_names as config_names  # noqa: E402
import clienttool_fax_ini as fax_ini  # noqa: E402
import clienttool_job_oids as job_oids  # noqa: E402
import clienttool_oid_semantics as oid_semantics  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT / "Kyocera" / "ClientTool"
CONFIG_OID_TABLE = (
    ROOT
    / "docs"
    / "reverse-engineering"
    / "data"
    / "clienttool-config-oids.tsv"
)
SUPPORT_XMLS = (
    ROOT
    / "Kyocera"
    / "ClientTool"
    / "WFH"
    / "remotefax"
    / "bin"
    / "conf"
    / "Support.xml",
    ROOT
    / "Kyocera"
    / "ClientTool"
    / "WFH"
    / "remotefax"
    / "addins"
    / "Host"
    / "Host.HostInfo"
    / "conf"
    / "Support.xml",
)
SEMANTICS_TABLE = (
    ROOT
    / "docs"
    / "reverse-engineering"
    / "data"
    / "clienttool-oid-semantics.tsv"
)
KYOCERA_ROOT = "1.3.6.1.4.1.1347."
ASCII_RE = re.compile(
    rb"(?<![\d.])(?:\.?)1\.3\.6\.1(?:\.\d{1,10}){2,}(?![\d.])"
)
UTF16_RE = re.compile(
    # In UTF-16LE a NUL character is two zero bytes, so the previous
    # character must be checked as a pair.  An earlier revision rejected a
    # preceding NUL and a trailing terminator, which hid every standalone
    # ``.1.3.6.1...`` literal in the #US heap.
    rb"(?<![0-9.]\x00)(?:\.\x00)?1\x00\.\x003\x00\.\x006\x00\.\x001\x00"
    rb"(?:(?:\.\x00)(?:\d\x00){1,10}){2,}(?![0-9.]\x00)"
)
UTF16_SIGNATURE = b"1\x00.\x003\x00"
ROOT_OIDS = {"1.3.6.1.2.1", "1.3.6.1.4.1.1347"}
LIBRARY_FILE_RE = re.compile(
    r"(?:BouncyCastle|itextsharp|MimeKit|log4net|SharpSnmpLib|Xceed|"
    r"SmartThreadPool|PasswordEncrypt|HelperClasses).*\.dll$",
    re.IGNORECASE,
)
COLUMNS = (
    "oid",
    "namespace",
    "oid_role",
    "symbols",
    "name_sources",
    "semantic_name",
    "prefix_symbols",
    "prefix_base_oid",
    "config_items",
    "config_descendant_items",
    "sources",
    "encodings",
    "occurrences",
)


def _normalize_oid(oid: str) -> str:
    return oid.strip().lstrip(".")


def extract_oids(data: bytes):
    """Yield ``(oid, offset, encoding)`` for each occurrence in *data*."""
    for match in ASCII_RE.finditer(data):
        yield (
            _normalize_oid(match.group().decode("ascii")),
            match.start(),
            "ascii",
        )
    if UTF16_SIGNATURE in data:
        for match in UTF16_RE.finditer(data):
            yield (
                _normalize_oid(match.group().decode("utf-16le")),
                match.start(),
                "utf16le",
            )


def _add_name(names: dict[str, list[tuple[str, str]]], oid: str, name: str, kind: str):
    values = names.setdefault(oid, [])
    if name and (name, kind) not in values:
        values.append((name, kind))


def load_names() -> dict[str, list[tuple[str, str]]]:
    names: dict[str, list[tuple[str, str]]] = {}
    for oid, symbols in config_names.merge_vendor_oids(
        config_names.DEFAULT_XMLS
    ).items():
        for symbol in symbols:
            _add_name(names, oid, symbol, "snmp-oid")
    for row in job_oids.expand_job_oids(job_oids.DEFAULT_XML):
        _add_name(names, row["oid"], row["symbol"], "job")
    for path in SUPPORT_XMLS:
        for element in ET.parse(path).getroot().iter():
            oid = (element.get("oid") or "").strip()
            if oid.startswith(".") or oid.startswith("1.3.6."):
                _add_name(
                    names,
                    _normalize_oid(oid),
                    element.tag.rsplit("}", 1)[-1],
                    "support",
                )
    for row in fax_ini.parse_ini(fax_ini.DEFAULT_INI):
        _add_name(names, row["oid"], row["name"], "fax-ini")
    return names


def _absolute_config_oid(oid: str) -> str:
    return oid if oid.startswith("1.3.6") else KYOCERA_ROOT + oid


def load_config_items() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with CONFIG_OID_TABLE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows.append(
                (row["item_id"], _absolute_config_oid(row["oid"]))
            )
    return rows


def _namespace(oid: str) -> str:
    if oid == "1.3.6.1.4.1.1347" or oid.startswith(KYOCERA_ROOT):
        return "kyocera"
    if (
        oid == "1.3.6.1.2.1"
        or oid.startswith("1.3.6.1.2.1.")
        or oid.startswith("1.3.6.1.5.5.7")
    ):
        return "standard"
    return "other"


def _sort_key(oid: str):
    return tuple(int(part) for part in oid.split("."))


def _is_library_constant(oid: str, source_files: list[str]) -> bool:
    """Non-printer OID literals coming only from bundled third-party libraries."""
    if _namespace(oid) == "kyocera" or not source_files:
        return False
    return all(LIBRARY_FILE_RE.search(path) for path in source_files)


def build_inventory(root: Path) -> list[dict[str, str]]:
    counts: dict[str, int] = Counter()
    sources: dict[str, Counter] = {}
    encodings: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        relative = path.relative_to(ROOT).as_posix()
        for oid, _start, encoding in extract_oids(data):
            counts[oid] += 1
            sources.setdefault(oid, Counter())[relative] += 1
            encodings.setdefault(oid, set()).add(encoding)

    names = load_names()
    semantics = {
        row["oid"]: row["semantic_name"]
        for row in oid_semantics.load_semantics(SEMANTICS_TABLE)
    }
    config_items = load_config_items()
    rows: list[dict[str, str]] = []
    for oid in sorted(counts, key=_sort_key):
        exact = names.get(oid, [])
        symbol_text = "|".join(sorted({name for name, _ in exact}))
        name_sources = "|".join(sorted({kind for _, kind in exact}))
        prefix_symbols = ""
        prefix_base = ""
        if not exact:
            parts = oid.split(".")
            for length in range(len(parts) - 1, 1, -1):
                candidate = ".".join(parts[:length])
                if candidate in names:
                    prefix_base = candidate
                    prefix_symbols = "|".join(
                        sorted({name for name, _ in names[candidate]})
                    )
                    break
        exact_items = [
            item_id for item_id, item_oid in config_items if item_oid == oid
        ]
        descendant_items = [
            item_id
            for item_id, item_oid in config_items
            if item_oid.startswith(oid + ".")
        ]
        source_text = ";".join(
            f"{source}:{count}"
            for source, count in sorted(sources[oid].items())
        )
        source_files = [
            item.rsplit(":", 1)[0] for item in source_text.split(";") if item
        ]
        if oid in ROOT_OIDS:
            role = "root"
        elif _is_library_constant(oid, source_files):
            role = "library-constant"
        else:
            role = "object"
        rows.append(
            {
                "oid": oid,
                "namespace": _namespace(oid),
                "oid_role": role,
                "symbols": symbol_text,
                "name_sources": name_sources,
                "semantic_name": semantics.get(oid, ""),
                "prefix_symbols": prefix_symbols,
                "prefix_base_oid": prefix_base,
                "config_items": "|".join(exact_items),
                "config_descendant_items": "|".join(descendant_items),
                "sources": source_text,
                "encodings": "|".join(sorted(encodings[oid])),
                "occurrences": str(counts[oid]),
            }
        )
    return rows


def format_tsv(rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in rows:
        lines.append(
            "\t".join(row[column].replace("\t", " ") for column in COLUMNS)
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    sys.stdout.write(format_tsv(build_inventory(args.root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
