"""Bounded reversible write audit for harmless configuration fields.

This module deliberately excludes network reachability, credentials, Wi-Fi,
fax identity, reset triggers, strings, and fields without an official mapping.
Every attempted field is restored to its baseline value before the next field.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .config import CONFIG
from .config_snapshot import compare_config_snapshots
from .snmp import BerError, SnmpClient

SAFE_AUDIT_FORMAT = "kyocera-client-safe-config-write-audit"
SAFE_AUDIT_VERSION = 1


@dataclass(frozen=True)
class SafeAuditField:
    item_id: int
    family: str
    alternate: Callable[[int], int | None]


def _step_down_or_up(value: int) -> int | None:
    if value < 0:
        return None
    return value - 1 if value > 0 else value + 1


def _toggle_01(value: int) -> int | None:
    return 1 - value if value in (0, 1) else None


def _media_weight(value: int) -> int | None:
    if value not in (11, 12, 13):
        return None
    return 11 if value != 11 else 12


def _print_density(value: int) -> int | None:
    if value not in (1, 2, 3, 4, 5):
        return None
    return 2 if value != 2 else 3


def _units(value: int) -> int | None:
    if value not in (3, 4):
        return None
    return 3 if value == 4 else 4


def _sleep_minutes(value: int) -> int | None:
    if value < 1:
        return None
    return 2 if value == 1 else 1


def _panel_clear_time(value: int) -> int | None:
    if value < 1:
        return None
    return value - 1


_MEDIA_WEIGHT_IDS = (11, 12, 14, 15, 17, 18, 19, 20, 24, 25, 26, 27, 28, 29, 30, 31, 32)

SAFE_AUDIT_FIELDS: tuple[SafeAuditField, ...] = (
    SafeAuditField(1, "sleep", _sleep_minutes),
    SafeAuditField(3, "timeout", _step_down_or_up),
    SafeAuditField(10, "paper mismatch handling", _toggle_01),
    *(
        SafeAuditField(item_id, "media weight", _media_weight)
        for item_id in _MEDIA_WEIGHT_IDS
    ),
    SafeAuditField(49, "print density", _print_density),
    SafeAuditField(51, "units", _units),
    SafeAuditField(52, "timeout", _step_down_or_up),
    SafeAuditField(84, "panel auto clear", _toggle_01),
    SafeAuditField(85, "panel clear time", _panel_clear_time),
)

_CONFIG_BY_ID = {item.item_id: item for item in CONFIG}


class ConfigWriteAuditError(ValueError):
    """Raised before the first write when the audit cannot run safely."""


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _read_integer(client: SnmpClient, oid: str) -> int:
    varbinds = client.get([oid], strict=True)
    if len(varbinds) != 1 or varbinds[0].oid != oid:
        raise BerError("SNMP readback did not return the requested OID")
    varbind = varbinds[0]
    if varbind.tag != 0x02:
        raise BerError(
            f"SNMP readback returned {varbind.type_name}, expected Integer"
        )
    return int(varbind.value)


def _wait_for_value(
    client: SnmpClient,
    oid: str,
    expected: int,
    *,
    timeout: float,
    interval: float,
) -> tuple[int | None, str | None]:
    deadline = time.monotonic() + max(timeout, 0)
    last_value: int | None = None
    last_error: str | None = None
    while True:
        try:
            last_value = _read_integer(client, oid)
            last_error = None
            if last_value == expected:
                return last_value, None
        except (BerError, OSError, TimeoutError, ValueError) as exc:
            last_error = _error_text(exc)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return last_value, last_error or f"expected {expected}, got {last_value}"
        time.sleep(min(interval, remaining))


def build_safe_audit_plan(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Build a write plan for readable, reversible harmless integer fields."""
    comparison = compare_config_snapshots(baseline, current)
    if comparison["changes"]:
        raise ConfigWriteAuditError(
            "configuration changed after the audit baseline was captured"
        )
    if comparison["read_status_changed"]:
        raise ConfigWriteAuditError(
            "configuration read status changed after the audit baseline was captured"
        )

    current_by_id = {
        record["item_id"]: record for record in current["objects"]
    }
    planned: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for field in SAFE_AUDIT_FIELDS:
        record = current_by_id[field.item_id]
        expected = _CONFIG_BY_ID[field.item_id]
        reason = None
        value = record.get("value")
        target = None
        if record.get("status") != 0:
            reason = "object_not_readable"
        elif record.get("value_kind") != "integer":
            reason = "value_not_integer"
        elif expected.type_code != 0:
            reason = "catalog_type_not_integer"
        elif not isinstance(value, int):
            reason = "value_missing"
        else:
            target = field.alternate(value)
            if target is None:
                reason = "current_value_outside_reviewed_range"

        entry = {
            "item_id": field.item_id,
            "label": record.get("label") or field.family,
            "family": field.family,
            "oid": record["absolute_oid"],
        }
        if reason is not None:
            entry["reason"] = reason
            skipped.append(entry)
            continue
        entry.update(
            {
                "before": value,
                "target": target,
                "readback_expected": target,
                "restore_expected": value,
            }
        )
        planned.append(entry)

    return {
        "format": SAFE_AUDIT_FORMAT,
        "version": SAFE_AUDIT_VERSION,
        "baseline_checksum": baseline["checksum"]["canonical_json"],
        "target": current["target"],
        "transport": current["transport"],
        "reviewed": len(SAFE_AUDIT_FIELDS),
        "planned": len(planned),
        "skipped": skipped,
        "fields": planned,
        "excluded_classes": [
            "network reachability",
            "SNMP credentials and traps",
            "Wi-Fi settings",
            "fax identity and notification",
            "reset triggers and counters",
            "strings and unknown semantics",
        ],
    }


def execute_safe_audit(
    client: SnmpClient,
    plan: dict[str, Any],
    *,
    readback_timeout: float = 2.0,
    readback_interval: float = 0.25,
) -> dict[str, Any]:
    """Exercise each planned field, always attempting restoration."""
    if plan.get("format") != SAFE_AUDIT_FORMAT:
        raise ConfigWriteAuditError("unrecognized safe-audit plan format")
    if plan.get("version") != SAFE_AUDIT_VERSION:
        raise ConfigWriteAuditError("unsupported safe-audit plan version")
    if plan.get("transport") != "snmp":
        raise ConfigWriteAuditError("safe audit supports SNMP only")
    if getattr(client, "host", None) != plan.get("target"):
        raise ConfigWriteAuditError("SNMP client target does not match audit plan")

    results: list[dict[str, Any]] = []
    aborted = False
    for field in plan["fields"]:
        if aborted:
            results.append(
                {
                    "item_id": field["item_id"],
                    "label": field["label"],
                    "oid": field["oid"],
                    "status": "not_attempted_after_failure",
                }
            )
            continue

        before = int(field["before"])
        target = int(field["target"])
        oid = field["oid"]
        result: dict[str, Any] = {
            "item_id": field["item_id"],
            "label": field["label"],
            "oid": oid,
            "before": before,
            "target": target,
            "status": "rollback_failed",
            "preflight_error": None,
            "set_target": {"attempted": False, "ok": False, "error": None},
            "verify_target": {
                "expected": target,
                "observed": None,
                "ok": False,
                "error": None,
            },
            "restore": {"attempted": False, "ok": False, "error": None},
            "verify_restore": {
                "expected": before,
                "observed": None,
                "ok": False,
                "error": None,
            },
        }

        try:
            observed_before = _read_integer(client, oid)
            if observed_before != before:
                result["preflight_error"] = (
                    f"value changed before write: expected {before}, "
                    f"got {observed_before}"
                )
                result["status"] = "preflight_changed"
                aborted = True
                results.append(result)
                continue
        except (BerError, OSError, TimeoutError, ValueError) as exc:
            result["preflight_error"] = _error_text(exc)
            result["status"] = "preflight_failed"
            aborted = True
            results.append(result)
            continue

        try:
            try:
                result["set_target"]["attempted"] = True
                client.set_integer(oid, target)
                result["set_target"]["ok"] = True
            except Exception as exc:
                result["set_target"]["error"] = _error_text(exc)

            observed, error = _wait_for_value(
                client,
                oid,
                target,
                timeout=readback_timeout,
                interval=readback_interval,
            )
            result["verify_target"] = {
                "expected": target,
                "observed": observed,
                "ok": observed == target,
                "error": error,
            }
        finally:
            try:
                result["restore"]["attempted"] = True
                client.set_integer(oid, before)
                result["restore"]["ok"] = True
            except Exception as exc:
                result["restore"]["error"] = _error_text(exc)

            observed, error = _wait_for_value(
                client,
                oid,
                before,
                timeout=readback_timeout,
                interval=readback_interval,
            )
            result["verify_restore"] = {
                "expected": before,
                "observed": observed,
                "ok": observed == before,
                "error": error,
            }

        target_ok = result["set_target"]["ok"] and result["verify_target"]["ok"]
        restore_ok = result["restore"]["ok"] and result["verify_restore"]["ok"]
        if target_ok and restore_ok:
            result["status"] = "success"
        elif restore_ok:
            result["status"] = "target_rejected_or_unverified"
        else:
            result["status"] = "rollback_failed"
            aborted = True
        results.append(result)

    attempted = [
        result
        for result in results
        if result["status"]
        not in ("not_attempted_after_failure",)
    ]
    successful = sum(result["status"] == "success" for result in attempted)
    restored = sum(
        result.get("verify_restore", {}).get("ok") is True
        for result in attempted
    )
    rollback_failed = any(
        result["status"] in ("preflight_changed", "preflight_failed", "rollback_failed")
        for result in attempted
    )
    return {
        "format": SAFE_AUDIT_FORMAT,
        "version": SAFE_AUDIT_VERSION,
        "status": "failed" if rollback_failed else "completed",
        "target": plan["target"],
        "transport": "snmp",
        "planned": len(plan["fields"]),
        "attempted": len(attempted),
        "successful": successful,
        "restored": restored,
        "skipped": plan["skipped"],
        "results": results,
    }
