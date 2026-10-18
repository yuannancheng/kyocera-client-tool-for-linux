# Contributing

Contributions must preserve the project's status as an independent,
unofficial interoperability tool.

## Allowed contributions

- Independently written Python code, tests and documentation.
- Factual protocol identifiers such as OIDs, request IDs, value types and
  high-level behavior summaries.
- Test fixtures that are synthetic, redacted or otherwise safe to publish.

## Do not submit

- Vendor installers, executables, DLLs, firmware, drivers or package archives.
- Complete decompiler output, copied vendor source code or large verbatim
  excerpts from vendor binaries or resources.
- Localized UI strings, dialog captions, menu descriptions, icons or other
  extracted vendor assets.
- Encryption keys, credentials, tokens, serial numbers, MAC addresses, Wi-Fi
  SSIDs or other device/user secrets.
- Local-only analysis directories, extracted files or tool caches.

## AI-assisted contributions

AI assistance does not remove copyright, patent or license obligations. Before
submitting AI-assisted code or documentation, a human contributor must:

1. check that it is not a verbatim copy of protected source or documentation;
2. identify any third-party code, data or algorithm that influenced it;
3. confirm that the chosen project license and any third-party licenses permit
   distribution;
4. keep vendor binaries and extracted assets out of the commit; and
5. run the tests and the publication check.

## Verification

Run:

```bash
python3 -m unittest discover -s tests -v
python3 tools/check_publication.py
```

The publication check is a guardrail, not a legal opinion. If a contribution
changes the protocol scope or adds a dependency, update
`docs/legal/compliance.md` and `THIRD_PARTY_NOTICES.md`.
