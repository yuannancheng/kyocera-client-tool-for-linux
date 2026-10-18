#!/usr/bin/env python3
"""Read .NET metadata constants and their owner fields/methods.

The ClientTool ships small .NET helper assemblies whose OID tables are stored
as metadata constants on static fields.  Loading such an assembly would execute
code, so this tool parses the PE/CLI headers, the ``#~`` metadata stream and the
``#Strings``/``#Blob`` heaps directly.  It is read only and never loads the
assembly.

Only the tables needed to resolve ``Constant`` owners are decoded: Module,
TypeRef, TypeDef, Field, MethodDef, Param, InterfaceImpl, MemberRef and
Constant.  Other table rows are skipped by size so the Constant table can be
located, but their contents are not interpreted.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


TABLE_NAMES = {
    0x00: "Module",
    0x01: "TypeRef",
    0x02: "TypeDef",
    0x03: "FieldPtr",
    0x04: "Field",
    0x05: "MethodPtr",
    0x06: "MethodDef",
    0x07: "ParamPtr",
    0x08: "Param",
    0x09: "InterfaceImpl",
    0x0A: "MemberRef",
    0x0B: "Constant",
    0x0C: "CustomAttribute",
    0x0D: "FieldMarshal",
    0x0E: "DeclSecurity",
    0x0F: "ClassLayout",
    0x10: "FieldLayout",
    0x11: "StandAloneSig",
    0x12: "EventMap",
    0x13: "EventPtr",
    0x14: "Event",
    0x15: "PropertyMap",
    0x16: "PropertyPtr",
    0x17: "Property",
    0x18: "MethodSemantics",
    0x19: "MethodImpl",
    0x1A: "ModuleRef",
    0x1B: "TypeSpec",
    0x1C: "ImplMap",
    0x1D: "FieldRVA",
    0x1E: "EncLog",
    0x1F: "EncMap",
    0x20: "Assembly",
    0x21: "AssemblyProcessor",
    0x22: "AssemblyOS",
    0x23: "AssemblyRef",
    0x24: "AssemblyRefProcessor",
    0x25: "AssemblyRefOS",
    0x26: "File",
    0x27: "ExportedType",
    0x28: "ManifestResource",
    0x29: "NestedClass",
    0x2A: "GenericParam",
    0x2B: "MethodSpec",
    0x2C: "GenericParamConstraint",
}

# Coded index definitions: (name, tables, tag bits)
CODED_INDEXES = {
    "TypeDefOrRef": ((0x02, 0x01, 0x1B), 2),
    "HasConstant": ((0x04, 0x08, 0x17), 2),
    "HasCustomAttribute": (
        (
            0x06,
            0x04,
            0x01,
            0x02,
            0x08,
            0x09,
            0x0A,
            0x00,
            0x0E,
            0x17,
            0x14,
            0x11,
            0x1A,
            0x15,
            0x1B,
            0x04,
            0x01,
            0x02,
            0x08,
            0x0A,
            0x1B,
        ),
        5,
    ),
    "CustomAttributeType": ((0x06, 0x0A, 0, 0, 0), 3),
    "ResolutionScope": ((0x00, 0x1A, 0x23, 0x01), 2),
    "MemberRefParent": ((0x02, 0x01, 0x1A, 0x06, 0x1B), 3),
    "HasSemantics": ((0x15, 0x17), 1),
    "MethodDefOrRef": ((0x06, 0x0A), 1),
    "MemberForwarded": ((0x04, 0x06), 1),
    "Implementation": ((0x26, 0x23, 0x25), 2),
    "CustomAttributeNamed": ((0x04, 0x08, 0x17), 2),
    "HasDeclSecurity": ((0x02, 0x06, 0x20), 2),
    "TypeOrMethodDef": ((0x02, 0x06), 1),
}


class MetadataError(ValueError):
    pass


@dataclass
class Section:
    name: str
    virtual_address: int
    virtual_size: int
    raw_size: int
    raw_pointer: int


class PeImage:
    def __init__(self, data: bytes) -> None:
        self.data = data
        if data[:2] != b"MZ":
            raise MetadataError("not a PE image (missing MZ)")
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_offset : pe_offset + 4] != b"PE\0\0":
            raise MetadataError("not a PE image (missing PE signature)")
        coff = pe_offset + 4
        machine, section_count = struct.unpack_from("<HH", data, coff)
        optional_size = struct.unpack_from("<H", data, coff + 16)[0]
        optional = coff + 20
        magic = struct.unpack_from("<H", data, optional)[0]
        if magic == 0x10B:
            directories = optional + 96
            self.is_pe32_plus = False
        elif magic == 0x20B:
            directories = optional + 112
            self.is_pe32_plus = True
        else:
            raise MetadataError(f"unsupported optional header magic 0x{magic:x}")
        self.machine = machine
        cli_rva, cli_size = struct.unpack_from("<II", data, directories + 14 * 8)
        if not cli_rva or not cli_size:
            raise MetadataError("image has no CLI header")
        section_table = optional + optional_size
        self.sections = []
        for index in range(section_count):
            base = section_table + index * 40
            name = data[base : base + 8].rstrip(b"\0").decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
                "<IIII", data, base + 8
            )
            self.sections.append(
                Section(name, virtual_address, virtual_size, raw_size, raw_pointer)
            )
        cli_offset = self.rva_to_offset(cli_rva)
        metadata_rva, metadata_size = struct.unpack_from(
            "<II", data, cli_offset + 8
        )
        self.metadata_offset = self.rva_to_offset(metadata_rva)
        self.metadata_size = metadata_size

    def rva_to_offset(self, rva: int) -> int:
        for section in self.sections:
            span = max(section.virtual_size, section.raw_size)
            if section.virtual_address <= rva < section.virtual_address + span:
                delta = rva - section.virtual_address
                if delta >= section.raw_size:
                    raise MetadataError(
                        f"RVA 0x{rva:x} falls in uninitialized section {section.name}"
                    )
                return section.raw_pointer + delta
        raise MetadataError(f"RVA 0x{rva:x} is not mapped")


class MetadataTables:
    def __init__(self, data: bytes, offset: int, size: int) -> None:
        self.data = data
        self.base = offset
        self.size = size
        if struct.unpack_from("<I", data, offset)[0] != 0x424A5342:
            raise MetadataError("bad metadata signature")
        version_length = struct.unpack_from("<I", data, offset + 12)[0]
        cursor = offset + 16 + version_length
        flags, stream_count = struct.unpack_from("<HH", data, cursor)
        self.flags = flags
        cursor += 4
        self.streams: dict[str, tuple[int, int]] = {}
        for _ in range(stream_count):
            stream_offset, stream_size = struct.unpack_from("<II", data, cursor)
            cursor += 8
            end = data.index(b"\0", cursor)
            name = data[cursor:end].decode("ascii")
            cursor = end + 1
            cursor = (cursor + 3) & ~3
            self.streams[name] = (offset + stream_offset, stream_size)
        if "#~" not in self.streams:
            raise MetadataError("metadata has no #~ table stream")
        table_offset, _ = self.streams["#~"]
        heap_sizes = data[table_offset + 6]
        self.string_index_size = 4 if heap_sizes & 0x01 else 2
        self.guid_index_size = 4 if heap_sizes & 0x02 else 2
        self.blob_index_size = 4 if heap_sizes & 0x04 else 2
        valid = struct.unpack_from("<Q", data, table_offset + 8)[0]
        row_counts = {}
        cursor = table_offset + 24
        for index in range(64):
            if valid & (1 << index):
                row_counts[index] = struct.unpack_from("<I", data, cursor)[0]
                cursor += 4
        self.row_counts = row_counts
        cursor = table_offset + 24 + 4 * len(row_counts)
        self.table_offsets: dict[int, int] = {}
        for index in range(64):
            if index not in row_counts:
                continue
            self.table_offsets[index] = cursor
            cursor += self.row_size(index) * row_counts[index]

    def index_size(self, table: int) -> int:
        return 4 if self.row_counts.get(table, 0) >= 0x10000 else 2

    def coded_size(self, name: str) -> int:
        tables, tag_bits = CODED_INDEXES[name]
        maximum = max(self.row_counts.get(table, 0) for table in tables)
        return 4 if maximum >= (1 << (16 - tag_bits)) else 2

    def row_size(self, table: int) -> int:
        string = self.string_index_size
        guid = self.guid_index_size
        blob = self.blob_index_size
        sizes = {
            0x00: 2 + string + guid * 3,
            0x01: self.coded_size("ResolutionScope") + string * 2,
            0x02: 4
            + string * 2
            + self.coded_size("TypeDefOrRef")
            + self.index_size(0x04) * 2,
            0x03: self.index_size(0x04),
            0x04: 2 + string + blob,
            0x05: self.index_size(0x06),
            0x06: 8 + string + blob + self.index_size(0x08),
            0x07: self.index_size(0x08),
            0x08: 4 + string,
            0x09: self.index_size(0x02) + self.coded_size("TypeDefOrRef"),
            0x0A: self.coded_size("MemberRefParent") + string + blob,
            0x0B: 1 + 1 + self.coded_size("HasConstant") + blob,
            0x0C: self.coded_size("HasCustomAttribute")
            + self.coded_size("CustomAttributeType")
            + blob,
            0x0D: self.index_size(0x04) + blob,
            0x0E: 2 + self.coded_size("HasDeclSecurity") + blob,
            0x0F: 2 + 4 + self.index_size(0x02),
            0x10: 4 + self.index_size(0x04),
            0x11: blob,
            0x12: self.index_size(0x02) + self.index_size(0x14),
            0x13: self.index_size(0x14),
            0x14: 2 + string + self.coded_size("TypeDefOrRef"),
            0x15: self.index_size(0x02) + self.index_size(0x17),
            0x16: self.index_size(0x17),
            0x17: 2 + string + blob,
            0x18: 2 + self.index_size(0x06) + self.coded_size("HasSemantics"),
            0x19: self.index_size(0x02)
            + self.coded_size("MethodDefOrRef")
            + self.coded_size("MethodDefOrRef"),
            0x1A: string,
            0x1B: blob,
            0x1C: 2 + self.coded_size("MemberForwarded") + string + self.index_size(0x1A),
            0x1D: 4 + self.index_size(0x04),
            0x1E: 4,
            0x1F: 4,
            0x20: 4 + 2 + 2 + 2 + 2 + 4 + blob + string * 2,
            0x21: 4,
            0x22: 4 + 4 + 4,
            0x23: 2 + 2 + 2 + 2 + 4 + blob + string * 2 + blob,
            0x24: 4 + 4,
            0x25: 4 + 4 + 4,
            0x26: 4 + string + blob,
            0x27: 4 + 4 + string + string + self.coded_size("Implementation"),
            0x28: 4 + 4 + string + self.coded_size("Implementation"),
            0x29: self.index_size(0x02) * 2,
            0x2A: 2 + 2 + self.coded_size("TypeOrMethodDef") + string,
            0x2B: self.coded_size("MethodDefOrRef") + blob,
            0x2C: self.index_size(0x2A) + self.coded_size("TypeDefOrRef"),
        }
        if table not in sizes:
            raise MetadataError(f"no row decoder for table 0x{table:x}")
        return sizes[table]

    def read_index(self, cursor: int, size: int) -> tuple[int, int]:
        if size == 2:
            return struct.unpack_from("<H", self.data, cursor)[0], cursor + 2
        return struct.unpack_from("<I", self.data, cursor)[0], cursor + 4

    def read_coded(self, cursor: int, name: str) -> tuple[int, int, int]:
        tables, tag_bits = CODED_INDEXES[name]
        value, cursor = self.read_index(cursor, self.coded_size(name))
        tag = value & ((1 << tag_bits) - 1)
        row = value >> tag_bits
        table = tables[tag] if tag < len(tables) else 0
        return table, row, cursor

    def string(self, index: int) -> str:
        offset, _ = self.streams["#Strings"]
        end = self.data.index(b"\0", offset + index)
        return self.data[offset + index : end].decode("utf-8", "replace")

    def blob(self, index: int) -> bytes:
        offset, _ = self.streams["#Blob"]
        cursor = offset + index
        length, cursor = self._compressed_uint(cursor)
        return self.data[cursor : cursor + length]

    def _compressed_uint(self, cursor: int) -> tuple[int, int]:
        first = self.data[cursor]
        if first & 0x80 == 0:
            return first, cursor + 1
        if first & 0xC0 == 0x80:
            value = ((first & 0x3F) << 8) | self.data[cursor + 1]
            return value, cursor + 2
        value = (
            ((first & 0x1F) << 24)
            | (self.data[cursor + 1] << 16)
            | (self.data[cursor + 2] << 8)
            | self.data[cursor + 3]
        )
        return value, cursor + 4

    def field_rows(self) -> dict[int, str]:
        if 0x04 not in self.row_counts:
            return {}
        base = self.table_offsets[0x04]
        size = self.row_size(0x04)
        names = {}
        for row in range(1, self.row_counts[0x04] + 1):
            name_index, _ = self.read_index(
                base + (row - 1) * size + 2, self.string_index_size
            )
            names[row] = self.string(name_index)
        return names

    def constant_rows(self) -> list[dict[str, object]]:
        if 0x0B not in self.row_counts:
            return []
        base = self.table_offsets[0x0B]
        size = self.row_size(0x0B)
        constants: list[dict[str, object]] = []
        for row in range(1, self.row_counts[0x0B] + 1):
            cursor = base + (row - 1) * size
            element_type = self.data[cursor]
            parent_table, parent_row, cursor = self.read_coded(
                cursor + 2, "HasConstant"
            )
            value_index, _ = self.read_index(cursor, self.blob_index_size)
            raw = self.blob(value_index)
            value: object
            if element_type == 0x0E:
                value = raw.decode("utf-16le", "replace").rstrip("\0")
            elif element_type == 0x03:
                value = raw.decode("utf-16le", "replace")
            elif element_type in (0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B):
                value = int.from_bytes(
                    raw, "little", signed=element_type in (0x04, 0x06, 0x08, 0x0A)
                )
            elif element_type == 0x02:
                value = bool(raw[0]) if raw else None
            elif element_type == 0x0C:
                value = struct.unpack("<f", raw)[0]
            elif element_type == 0x0D:
                value = struct.unpack("<d", raw)[0]
            else:
                value = raw.hex()
            constants.append(
                {
                    "row": row,
                    "element_type": f"0x{element_type:02x}",
                    "owner_table": TABLE_NAMES.get(parent_table, hex(parent_table)),
                    "owner_row": parent_row,
                    "value": value,
                }
            )
        return constants


def decode_constants(path: Path) -> list[dict[str, object]]:
    image = PeImage(path.read_bytes())
    tables = MetadataTables(image.data, image.metadata_offset, image.metadata_size)
    fields = tables.field_rows()
    result = []
    for item in tables.constant_rows():
        item = dict(item)
        if item["owner_table"] == "Field":
            item["owner"] = fields.get(int(item["owner_row"]), "")
        result.append(item)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--owner", help="case-insensitive substring of the field name")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rows = decode_constants(args.path)
    if args.owner:
        needle = args.owner.lower()
        rows = [row for row in rows if needle in str(row.get("owner", "")).lower()]
    if args.json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for row in rows:
            print(f"{row.get('owner', '')}\t{row['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
