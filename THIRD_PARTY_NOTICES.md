# Third-Party Notices

This repository does not vendor third-party source code or binary packages.

The core command-line implementation uses only the Python standard library.
The optional native GUI uses the system-provided GTK 3 and WebKit2GTK
libraries. Those libraries are not bundled with this repository; their
licenses and notices are supplied by the operating-system packages that
provide them.

Some research tools may be run locally against a user-supplied vendor
installation or use optional Python packages installed by the user. Those
local tools, external dependencies and extracted artifacts are not part of the
public source distribution.

Kyocera, KYOCERA, ECOSYS, MA2000w and related marks belong to their respective
owners. See [NOTICE](NOTICE) for the trademark and non-affiliation statement.

If a future contribution adds a third-party dependency or copies third-party
code, the contributor must update this file with the component name, version,
license, source URL and required notices before merging.
