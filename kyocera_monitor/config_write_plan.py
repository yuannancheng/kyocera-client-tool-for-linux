"""Dry-run plans for carefully reviewed single-field configuration writes.

This module validates a baseline against a fresh configuration read and
produces a reviewable plan with command previews and rollback information.  It
never opens a device channel and never sends a write command.  Planning a field
does not imply that the current build has an authorized executor for it.
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
WRITE_PLAN_VERSION = 2

AUTHORIZATION_SCOPE = "auto-error-clear-off-to-on-then-off-v1"


class ConfigWritePlanError(ValueError):
    """Raised when a requested write cannot be represented safely."""


@dataclass(frozen=True)
class SafeIntegerSetting:
    item_id: int
    choices: dict[int, str]
    reason: str
    authorization_scope: str
    execution_blockers: tuple[str, ...] = ()
    authorized_transition: tuple[int, int] | None = None
    execution_note: str = ""


# Candidates intentionally have tiny, independently evidenced state spaces.
# They may generate audit-only plans even when no device-write executor is
# authorized.  Add fields only after their official mapping is verified.
SAFE_INTEGER_SETTINGS: dict[int, SafeIntegerSetting] = {
    2: SafeIntegerSetting(
        item_id=2,
        choices={0: "OFF", 1: "ON"},
        reason=(
            "Native main-dialog control 0x03ea maps to model offset 0x0004 "
            "and OID 43.5.1.1.34.1; the official binary and device reads "
            "establish an integer ON/OFF setting."
        ),
        authorization_scope=AUTHORIZATION_SCOPE,
        authorized_transition=(0, 1),
        execution_note=(
            "Execution is limited to Auto error clear OFF -> ON -> OFF. "
            "A matching confirmation token is required, and rollback is "
            "attempted even when the forward write or readback fails."
        ),
    ),
    50: SafeIntegerSetting(
        item_id=50,
        choices={0: "OFF", 1: "ON"},
        reason=(
            "Native main-dialog control 0x0455 maps through snapshot offset "
            "0x0018 and diff case 0x31 to OID 1001.2.1.1.1.14.1. The official "
            "binary serializes it as integer 0/1; no device write/readback "
            "experiment has established acceptance or reboot behavior."
        ),
        authorization_scope="no-device-write-authorized-v1",
        execution_blockers=(
            "same_oid_write_readback_unverified",
            "device_failure_and_reboot_behavior_unverified",
            "executor_not_implemented",
            "explicit_user_authorization_required",
        ),
        execution_note=(
            "This is an audit-only plan. Quiet mode has a statically verified "
            "serialization path, but no executor is authorized and no write "
            "command may be derived from this plan for device execution."
        ),
    ),
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
    if candidate.authorized_transition is not None and (
        before_value,
        requested_value,
    ) != candidate.authorized_transition:
        blockers.append("outside_authorized_experiment")

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
    execution_blockers = list(blockers)
    for blocker in candidate.execution_blockers:
        if blocker not in execution_blockers:
            execution_blockers.append(blocker)
    executor_supported = candidate.authorized_transition is not None

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
            "plan_preconditions_valid": not blockers,
            "executor_supported": executor_supported,
            "ready_for_executor_implementation": (
                not blockers and executor_supported
            ),
            "blockers": blockers,
        },
        "execution": {
            "allowed": not blockers and executor_supported,
            "requires_confirmation_token": True,
            "authorization_scope": candidate.authorization_scope,
            "blockers": execution_blockers,
            "note": candidate.execution_note,
        },
    }
    confirmation_payload = {
        "format": payload["format"],
        "version": payload["version"],
        "baseline_checksum": payload["baseline"]["checksum"],
        "target": payload["target"],
        "transport": payload["transport"],
        "object": payload["object"],
        "before": payload["before"],
        "current": payload["current"],
        "requested": payload["requested"],
        "rollback": payload["rollback"],
        "verification": payload["verification"],
        "review": payload["review"],
        "execution": payload["execution"],
    }
    digest = _plan_digest(confirmation_payload)
    payload["confirmation"] = {
        "algorithm": "sha256",
        "token": digest,
    }
    return payload
