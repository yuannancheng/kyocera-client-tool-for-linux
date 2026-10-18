#!/usr/bin/env python3
"""Command-line wrapper for the read-only SNMP probe.

The implementation lives in ``kyocera_monitor.snmp`` so the probe and the
monitor share one protocol code path.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kyocera_monitor.snmp import main


if __name__ == "__main__":
    raise SystemExit(main())
