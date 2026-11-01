"""Dry-run plans for the first carefully selected configuration write.

This module validates a baseline against a fresh configuration read and
produces a reviewable plan with command previews and rollback information.  It
never opens a device channel and never sends a write command.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import CONFIG
from .config_snapshot import compare_config_snapshots

WRITE_PLAN_FORMAT = "kyocera-client-config-write-plan"
WRITE_PLAN_VERSION = 1

EXECUTION_BLOCKERS = (
    "write_executor_disabled",
    "real_device_write_and_rollback_not_verified",
)


class ConfigWritePlanError(ValueError):
    """Raised when a requested write cannot be represented safely."""


@dataclass(frozen=True)
class SafeIntegerSetting:
    item_id: int
    choices: dict[int, str]
    reason: str


# The first write candidate intentionally has a tiny, independently evidenced
# state space.  Add fields only after their official mapping and rollback
# behavior have equally strong evidence.
SAFE_INTEGER_SETTINGS: dict[int, SafeIntegerSetting] = {
    2: SafeIntegerSetting(
        item_id=2,
        choices={0: "OFF", 1: "ON"},
        reason=(
            "Native main-dialog control 0x03ea maps to model offset 0x0004 "
            "and OID 43.5.1.1.34.1; the official binary and device reads "
            "establish an integer ON/OFF setting."
        ),
    )
}

_ASSIGNMENT_RE = re.compile(r"^\s*(\d+)\s*=\s*([^=\s]+)\s*$")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _plan_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def parse_config_assignment(text: str) -> tuple[int, str]:
    """Parse ``ITEM_ID=VALUE`` without accepting extra shell-like syntax."""
    match = _ASSIGNMENT_RE.fullmatch(text)
    if match is None:
        raise ConfigWritePlanError(
            "configuration assignment must use ITEM_ID=VALUE"
        )
    return int(match.group(1)), match.group(2)


def _parse_requested_value(candidate: SafeIntegerSetting, text: str) -> int:
    normalized = text.strip().upper()
    for value, label in candidate.choices.items():
        if normalized == label.upper() or normalized == str(value):
            return value
    allowed = ", ".join(
        f"{label}={value}" for value, label in candidate.choices.items()
    )
    raise ConfigWritePlanError(
        f"item {candidate.item_id} accepts only {allowed}; got {text!r}"
    )


def _object_record(snapshot: dict[str, Any], item_id: int) -> dict[str, Any]:
    return next(
        record for record in snapshot["objects"] if record["item_id"] == item_id
    )


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": record.get("status"),
        "value": record.get("value"),
        "display": record.get("display"),
        "raw_value": record.get("raw_value"),
    }


def build_config_write_plan(
    baseline: dict[str, Any],
    current: dict[str, Any],
    assignment: str,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a dry-run plan after checking all currently required safeguards."""
    item_id, requested_text = parse_config_assignment(assignment)
    candidate = SAFE_INTEGER_SETTINGS.get(item_id)
    if candidate is None:
        allowed = ", ".join(str(value) for value in SAFE_INTEGER_SETTINGS)
        raise ConfigWritePlanError(
            f"item {item_id} is not an approved write-plan candidate; "
            f"allowed item ids: {allowed}"
        )
    requested_value = _parse_requested_value(candidate, requested_text)

    comparison = compare_config_snapshots(baseline, current)
    before_record = _object_record(baseline, item_id)
    current_record = _object_record(current, item_id)
    expected = next(obj for obj in CONFIG if obj.item_id == item_id)
    if expected.type_code != 0:
        raise ConfigWritePlanError(
            f"item {item_id} is not represented as an integer"
        )

    blockers: list[str] = []
    if before_record.get("status") != 0:
        blockers.append("baseline_object_not_readable")
    if current_record.get("status") != 0:
        blockers.append("current_object_not_readable")
    before_value = before_record.get("value")
    current_value = current_record.get("value")
    if before_record.get("status") == 0 and before_value not in candidate.choices:
        blockers.append("unsupported_baseline_value")
    if current_record.get("status") == 0 and current_value not in candidate.choices:
        blockers.append("unsupported_current_value")
    if comparison["changes"]:
        blockers.append("unexpected_configuration_drift")
    if comparison["read_status_changed"]:
        blockers.append("unstable_configuration_read")
    if current_value == requested_value and current_record.get("status") == 0:
        blockers.append("requested_value_equals_current_value")

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ConfigWritePlanError("write plan timestamp must include a timezone")

    pjl_line = (
        f'@PJL KSETOBJ OBJ="{expected.pjl_object}" VALUE ={requested_value}'
    )
    rollback_is_valid = (
        before_record.get("status") == 0
        and before_value in candidate.choices
    )
    rollback_line = (
        f'@PJL KSETOBJ OBJ="{expected.pjl_object}" VALUE ={before_value}'
        if rollback_is_valid
        else None
    )
    payload: dict[str, Any] = {
        "format": WRITE_PLAN_FORMAT,
        "version": WRITE_PLAN_VERSION,
        "created_at": timestamp.astimezone(timezone.utc).isoformat(),
        "baseline": {
            "created_at": baseline["created_at"],
            "target": baseline["target"],
            "transport": baseline["transport"],
            "checksum": baseline["checksum"]["canonical_json"],
        },
        "target": current["target"],
        "transport": current["transport"],
        "object": {
            "item_id": item_id,
            "oid": expected.oid,
            "absolute_oid": current_record["absolute_oid"],
            "pjl_object": expected.pjl_object,
            "label": current_record.get("label") or expected.oid,
            "type_code": expected.type_code,
            "value_type": "integer",
            "reason": candidate.reason,
        },
        "before": _record_summary(before_record),
        "current": _record_summary(current_record),
        "requested": {
            "value": requested_value,
            "display": candidate.choices[requested_value],
        },
        "rollback": {
            "value": before_value,
            "display": candidate.choices.get(before_value),
        },
        "preconditions": {
            "target_matches": comparison["target_matches"],
            "transport_matches": baseline["transport"] == current["transport"],
            "persistent_config_changes": comparison["changed"],
            "read_status_changes": comparison["read_status_changed"],
            "volatile_observations_changed": comparison["volatile_changed"],
        },
        "unexpected_config_changes": [
            {"item_id": change["item_id"], "label": change["label"]}
            for change in comparison["changes"]
        ],
        "read_status_changes": [
            {"item_id": change["item_id"], "label": change["label"]}
            for change in comparison["read_status_changes"]
        ],
        "commands": {
            "pjl_line": pjl_line,
            "pjl_rollback_line": rollback_line,
            "snmp_set": {
                "oid": current_record["absolute_oid"],
                "syntax": "Integer",
                "value": requested_value,
            },
            "snmp_rollback": {
                "oid": current_record["absolute_oid"],
                "syntax": "Integer",
                "value": before_value if rollback_is_valid else None,
            },
        },
        "verification": {
            "read_item_id": item_id,
            "expected_value": requested_value,
            "rollback_value": before_value,
            "require_status_zero": True,
        },
        "review": {
            "ready_for_executor_implementation": not blockers,
            "blockers": blockers,
        },
        "execution": {
            "allowed": False,
            "blockers": list(EXECUTION_BLOCKERS),
            "note": (
                "The public CLI never sends this plan. A future executor must "
                "require a new explicit confirmation and real-device rollback "
                "evidence."
            ),
        },
    }
    digest = _plan_digest(payload)
    payload["confirmation"] = {
        "algorithm": "sha256",
        "token": digest,
    }
    return payload
