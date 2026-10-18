# Publication and Compliance Notes

This document records the project's publication boundary. It is an engineering
policy, not legal advice; a final release should still be reviewed by a
qualified lawyer when the risk profile warrants it.

## Project position

This is an independent, unofficial Linux status monitor for Kyocera printers.
It is not affiliated with, authorized by, sponsored by, endorsed by, or
approved by Kyocera Corporation or its affiliates. Kyocera and related names
are used only to identify compatibility targets. See [NOTICE](../../NOTICE).

The implementation is independently written. Protocol identifiers and
high-level behavior observations are documented to support interoperability;
they are not intended to reproduce vendor source code or creative assets.
Vendor symbol names retained in OID tables are used only as factual
interoperability identifiers. They are not reproduced source code, UI text or
creative documentation; if a rights holder raises a concern, the full symbol
indexes can be moved to the ignored local-only analysis tree.

## Public content

The following may be published:

- independently written source code, tests and build metadata;
- OIDs, request IDs, type codes and short factual behavior summaries;
- synthetic or redacted fixtures that contain no vendor asset and no personal
  or device-sensitive value;
- license, notice, trademark and third-party dependency documentation.

## Restricted content

The following must stay outside the public tree, normally under the ignored
`analysis/` directory:

- vendor installers, EXE/DLL files, firmware, drivers and archives;
- complete decompiler output, pseudocode dumps and symbol dumps that reproduce
  vendor implementation details at scale;
- extracted UI strings, dialog captions, menu descriptions, icons and other
  vendor resources;
- encryption keys, IVs, package decryption tools and extracted package
  contents;
- credentials, tokens, serial numbers, MAC addresses, Wi-Fi SSIDs and logs
  containing them.

## Data minimization

Public TSV and JSON research files should carry only the fields needed for
interoperability. Raw byte context, localized text and free-form vendor
descriptions should not be emitted. When a field is sensitive, store a boolean,
length, hash or category instead of the value.

## AI-assisted work

AI-generated or AI-assisted material is treated as contributor-supplied
material. It is not assumed to be free of copyright, patent or license
obligations. Contributors must review provenance, avoid verbatim reproduction
of protected material, record third-party components and run the publication
check before release.

## Release checklist

1. `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md` are present and accurate.
2. README states the independent, unofficial status and the warranty/liability
   disclaimer.
3. `git ls-files` contains no vendor binary, archive, extracted asset, key or
   credential.
4. Research data contains no raw byte context, UI text or menu descriptions.
5. `python3 tools/check_publication.py` passes.
6. `python3 -m unittest discover -s tests -v` passes.
7. Public Git history has been scanned and purged of restricted files;
   deleting a file in a new commit is not sufficient.
8. A human has reviewed new AI-assisted code and any changed third-party
   dependency for license and provenance.

## Reporting a concern

If a file appears to contain protected vendor material, a secret or personal
data, do not redistribute it. Remove it from the public tree, preserve an
ignored local copy if needed, and open an issue describing the category and
location without repeating the sensitive value.
