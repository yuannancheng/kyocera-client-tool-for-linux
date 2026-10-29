#!/usr/bin/env python3
"""Command-line wrapper for the read-only KM-WSDL scan service probe."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kyocera_monitor.kmscn import main


if __name__ == "__main__":
    raise SystemExit(main())
