"""Execute user-mapped local presets for observed Push Scan requests.

The device status code is an official signal, while the mapping from a
0-30 Quick Scan slot to a Linux-local preset is an explicit user choice.
This module does not write the Push Scan result object: the official scan
application chain shows how the result is serialized, but not which process
decides when a scan is complete.
"""

from __future__ import annotations

from pathlib import Path

from .preferences import (
    MAX_PUSH_SCAN_PRESET,
    SettingsError,
    preset_for_push_scan_slot,
)
from .scan import ScanBusyError, ScanJobManager, ScanOptions


def _scan_timeout(options: ScanOptions) -> float:
    """Bound a local wait without cutting off normal device polling."""

    return min(
        3600.0,
        max(
            30.0,
            options.max_polls * (options.timeout + options.poll_interval) + 60,
        ),
    )


def execute_push_scan_event(
    event: dict[str, object],
    settings: dict[str, object],
    manager: ScanJobManager,
    *,
    push_state: dict[str, object],
) -> dict[str, object]:
    """Run the local preset mapped to an observed Push Scan slot.

    An unmapped or busy slot is reported as a non-execution result. A matching
    preset is submitted through the normal scan job manager, including its
    configured output directory, busy protection and bounded completion wait.
    """

    host = event.get("host")
    slot = event.get("preset_number")
    if not isinstance(host, str) or not host:
        raise ValueError("Push Scan event has no valid host")
    if (
        isinstance(slot, bool)
        or not isinstance(slot, int)
        or not 0 <= slot <= MAX_PUSH_SCAN_PRESET
    ):
        raise SettingsError(
            f"Push Scan slot must be an integer from 0 to {MAX_PUSH_SCAN_PRESET}"
        )
    readiness = push_state.get("readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not True:
        return {
            "mode": "local_preset_mapping",
            "status": "not_ready",
            "host": host,
            "preset_number": slot,
            "preset": None,
            "job": None,
            "readiness_state": (
                readiness.get("state")
                if isinstance(readiness, dict)
                else "unavailable"
            ),
            "result_writeback": "not_attempted",
        }
    preset = preset_for_push_scan_slot(settings, slot)
    if preset is None:
        return {
            "mode": "local_preset_mapping",
            "status": "unmapped",
            "host": host,
            "preset_number": slot,
            "preset": None,
            "job": None,
            "result_writeback": "not_attempted",
        }

    options = ScanOptions(
        color=preset["color"],
        resolution=preset["resolution"],
        original_image=preset["original_image"],
        output_format=preset["output_format"],
        max_pages=preset["max_pages"],
    )
    try:
        job = manager.start(
            host,
            options,
            output_directory=Path(str(settings["scan_directory"])),
        )
    except ScanBusyError as error:
        return {
            "mode": "local_preset_mapping",
            "status": "busy",
            "host": host,
            "preset_number": slot,
            "preset": {
                "id": preset["id"],
                "name": preset["name"],
            },
            "job": None,
            "error": str(error),
            "result_writeback": "not_attempted",
        }

    try:
        completed = manager.wait(job.job_id, timeout=_scan_timeout(options))
    except TimeoutError as error:
        return {
            "mode": "local_preset_mapping",
            "status": "incomplete",
            "host": host,
            "preset_number": slot,
            "preset": {
                "id": preset["id"],
                "name": preset["name"],
            },
            "job": job.metadata(),
            "error": str(error),
            "result_writeback": "not_attempted",
        }
    return {
        "mode": "local_preset_mapping",
        "status": completed.state,
        "host": host,
        "preset_number": slot,
        "preset": {
            "id": preset["id"],
            "name": preset["name"],
        },
        "job": completed.metadata(),
        "result_writeback": "not_attempted",
    }


__all__ = ["execute_push_scan_event"]
