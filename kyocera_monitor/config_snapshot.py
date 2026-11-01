"""Portable, integrity-checked snapshots of printer configuration reads.

Snapshots are a prerequisite for any future configuration write support.  They
preserve both decoded values and the values observed on the transport so a
later implementation can prove the baseline, detect drift, and prepare a
rollback.  This module never sends a write command.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import CONFIG, ConfigObject, absolute_config_oid

SNAPSHOT_FORMAT = "kyocera-client-config-snapshot"
SNAPSHOT_VERSION = 2
SNAPSHOT_SOURCE = "clienttool-1.4.11.2 config objects"
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024

_CONFIG_BY_ID: dict[int, ConfigObject] = {obj.item_id: obj for obj in CONFIG}
_SNAPSHOT_FIELDS = (
    "item_id",
    "oid",
    "absolute_oid",
    "pjl_object",
    "type_code",
    "status",
    "error",
    "value_kind",
    "value",
    "display",
    "raw_value",
    "pjl_type",
    "snmp_type",
    "label",
    "vendor_name",
    "confidence",
    "sensitive",
    "volatile",
)
_OPTIONAL_RECORD_FIELDS = (
    "error",
    "value_kind",
    "value",
    "display",
    "raw_value",
    "pjl_type",
    "snmp_type",
    "label",
    "vendor_name",
    "confidence",
)
_SENSITIVE_OIDS = {
    "1.3.6.1.2.1.1.4.0",  # sysContact
    "1.3.6.1.2.1.1.6.0",  # sysLocation
    absolute_config_oid("40.26.2.1.3.1"),  # SNMP read community
    absolute_config_oid("40.26.2.1.4.1"),  # SNMP write community
    absolute_config_oid("40.42.1.1.4.1"),  # Wi-Fi SSID
}
_VOLATILE_ITEMS = {
    142,  # Wi-Fi connection state
    146,  # Wi-Fi RSSI
    147,  # Wi-Fi channel
}


class ConfigSnapshotError(ValueError):
    """Raised when a configuration snapshot is unsafe or malformed."""


def _json_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigSnapshotError(
            f"configuration snapshot is not JSON-serializable: {exc}"
        ) from exc
    return text.encode("utf-8")


def _checksum(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "algorithm": "sha256",
        "canonical_json": hashlib.sha256(_json_bytes(payload)).hexdigest(),
    }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigSnapshotError(
                f"configuration snapshot contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _validate_scalar(value: object, field: str, item_id: int) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise ConfigSnapshotError(
        f"item {item_id} field {field!r} is not a JSON scalar"
    )


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    try:
        item_id = int(record["item_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigSnapshotError("configuration record has no valid item_id") from exc

    expected = _CONFIG_BY_ID.get(item_id)
    if expected is None:
        raise ConfigSnapshotError(f"unknown configuration item id: {item_id}")
    if record.get("oid") != expected.oid:
        raise ConfigSnapshotError(
            f"item {item_id} OID mismatch: {record.get('oid')!r} != {expected.oid!r}"
        )

    absolute_oid = (
        record.get("absolute_oid") or absolute_config_oid(expected.oid)
    )
    if absolute_oid != absolute_config_oid(expected.oid):
        raise ConfigSnapshotError(
            f"item {item_id} absolute OID mismatch: {absolute_oid!r}"
        )
    type_code = record.get("type_code", expected.type_code)
    if type_code != expected.type_code:
        raise ConfigSnapshotError(
            f"item {item_id} type mismatch: {type_code!r}"
        )
    status = record.get("status")
    if status is not None and not isinstance(status, int):
        raise ConfigSnapshotError(f"item {item_id} status is not an integer")

    normalized: dict[str, Any] = {
        "item_id": item_id,
        "oid": expected.oid,
        "absolute_oid": absolute_oid,
        "pjl_object": expected.pjl_object,
        "type_code": expected.type_code,
        "status": status,
        "sensitive": absolute_oid in _SENSITIVE_OIDS,
        "volatile": item_id in _VOLATILE_ITEMS,
    }
    for field in _OPTIONAL_RECORD_FIELDS:
        if field in record:
            _validate_scalar(record[field], field, item_id)
            normalized[field] = record[field]
    return normalized


def build_config_snapshot(
    records: Iterable[dict[str, Any]],
    *,
    transport: str,
    target: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a validated snapshot from one complete 147-object read."""
    if transport not in {"pjl", "snmp"}:
        raise ConfigSnapshotError(f"unsupported configuration transport: {transport!r}")
    if not isinstance(target, str) or not target.strip():
        raise ConfigSnapshotError("configuration snapshot requires a target")

    normalized = [_normalize_record(record) for record in records]
    normalized.sort(key=lambda record: record["item_id"])
    if len(normalized) != len(CONFIG):
        raise ConfigSnapshotError(
            f"expected {len(CONFIG)} configuration objects, got {len(normalized)}"
        )
    item_ids = [record["item_id"] for record in normalized]
    if item_ids != list(range(1, len(CONFIG) + 1)):
        raise ConfigSnapshotError(
            "configuration snapshot must contain each item id exactly once"
        )

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ConfigSnapshotError("snapshot timestamp must include a timezone")
    payload: dict[str, Any] = {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "created_at": timestamp.astimezone(timezone.utc).isoformat(),
        "source": SNAPSHOT_SOURCE,
        "transport": transport,
        "target": target,
        "read": sum(record["status"] == 0 for record in normalized),
        "total": len(normalized),
        "objects": normalized,
    }
    payload["checksum"] = _checksum(payload)
    return payload


def _validate_snapshot(snapshot: object) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ConfigSnapshotError("configuration snapshot root must be an object")
    required = {
        "format",
        "version",
        "created_at",
        "source",
        "transport",
        "target",
        "read",
        "total",
        "objects",
        "checksum",
    }
    missing = required - snapshot.keys()
    extra = snapshot.keys() - required
    if missing or extra:
        raise ConfigSnapshotError(
            "configuration snapshot fields differ from the supported schema"
        )
    if snapshot["format"] != SNAPSHOT_FORMAT:
        raise ConfigSnapshotError("unrecognized configuration snapshot format")
    if snapshot["version"] != SNAPSHOT_VERSION:
        raise ConfigSnapshotError(
            f"unsupported configuration snapshot version: {snapshot['version']!r}"
        )
    if snapshot["source"] != SNAPSHOT_SOURCE:
        raise ConfigSnapshotError("unexpected configuration snapshot source")
    if not isinstance(snapshot["created_at"], str):
        raise ConfigSnapshotError("configuration snapshot timestamp is not text")
    if not isinstance(snapshot["transport"], str):
        raise ConfigSnapshotError("configuration snapshot transport is not text")
    if not isinstance(snapshot["target"], str):
        raise ConfigSnapshotError("configuration snapshot target is not text")
    if not isinstance(snapshot["objects"], list):
        raise ConfigSnapshotError("configuration snapshot objects must be a list")
    allowed_record_fields = set(_SNAPSHOT_FIELDS)
    for record in snapshot["objects"]:
        if not isinstance(record, dict):
            raise ConfigSnapshotError(
                "configuration snapshot object entries must be objects"
            )
        unexpected = record.keys() - allowed_record_fields
        if unexpected:
            raise ConfigSnapshotError(
                "configuration snapshot contains unsupported object fields"
            )

    checksum = snapshot["checksum"]
    if (
        not isinstance(checksum, dict)
        or checksum.get("algorithm") != "sha256"
        or not isinstance(checksum.get("canonical_json"), str)
    ):
        raise ConfigSnapshotError("configuration snapshot checksum is malformed")
    payload = {key: value for key, value in snapshot.items() if key != "checksum"}
    if checksum != _checksum(payload):
        raise ConfigSnapshotError("configuration snapshot checksum does not match")

    try:
        created_at = datetime.fromisoformat(snapshot["created_at"])
    except ValueError as exc:
        raise ConfigSnapshotError("configuration snapshot timestamp is invalid") from exc
    normalized = build_config_snapshot(
        snapshot["objects"],
        transport=snapshot["transport"],
        target=snapshot["target"],
        created_at=created_at,
    )
    if normalized["checksum"] != checksum:
        raise ConfigSnapshotError("configuration snapshot content is inconsistent")
    if snapshot["read"] != normalized["read"] or snapshot["total"] != normalized["total"]:
        raise ConfigSnapshotError("configuration snapshot read counts are inconsistent")
    return snapshot


def save_config_snapshot(
    path: str | os.PathLike[str],
    snapshot: dict[str, Any],
    *,
    overwrite: bool = False,
) -> Path:
    """Atomically save one snapshot with owner-only permissions."""
    destination = Path(path).expanduser()
    parent = destination.parent
    if not parent.is_dir():
        raise ConfigSnapshotError(f"snapshot directory does not exist: {parent}")
    if destination.exists() and not overwrite:
        raise ConfigSnapshotError(
            f"refusing to overwrite existing snapshot: {destination}"
        )
    _validate_snapshot(snapshot)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(_json_bytes(snapshot) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, destination)
        else:
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise ConfigSnapshotError(
                    f"refusing to overwrite existing snapshot: {destination}"
                ) from exc
            temporary.unlink()
        os.chmod(destination, 0o600)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def load_config_snapshot(
    path: str | os.PathLike[str],
    *,
    require_private: bool = True,
) -> dict[str, Any]:
    """Load and verify a snapshot, refusing group/world-readable files."""
    source = Path(path).expanduser()
    try:
        details = source.stat()
    except OSError as exc:
        raise ConfigSnapshotError(f"cannot read configuration snapshot: {source}") from exc
    if not stat.S_ISREG(details.st_mode):
        raise ConfigSnapshotError("configuration snapshot must be a regular file")
    if details.st_size > MAX_SNAPSHOT_BYTES:
        raise ConfigSnapshotError("configuration snapshot is unexpectedly large")
    if require_private and details.st_mode & 0o077:
        raise ConfigSnapshotError(
            "configuration snapshot is readable by group or others; chmod 600 it"
        )
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise ConfigSnapshotError(f"cannot read configuration snapshot: {source}") from exc
    try:
        snapshot = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except UnicodeDecodeError as exc:
        raise ConfigSnapshotError("configuration snapshot is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ConfigSnapshotError("configuration snapshot is not valid JSON") from exc
    return _validate_snapshot(snapshot)


def _record_change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_value = {
        key: before.get(key)
        for key in (
            "status",
            "error",
            "value_kind",
            "value",
            "display",
            "raw_value",
        )
    }
    after_value = {
        key: after.get(key)
        for key in (
            "status",
            "error",
            "value_kind",
            "value",
            "display",
            "raw_value",
        )
    }
    return {
        "item_id": after["item_id"],
        "oid": after["oid"],
        "label": (
            after.get("label")
            or after.get("vendor_name")
            or after.get("pjl_object")
            or after["oid"]
        ),
        "before": before_value,
        "after": after_value,
        "sensitive": bool(before.get("sensitive") or after.get("sensitive")),
    }


def compare_config_snapshots(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    allow_target_mismatch: bool = False,
) -> dict[str, Any]:
    """Return semantic changes while refusing transport or target mismatches."""
    baseline = _validate_snapshot(baseline)
    current = _validate_snapshot(current)
    if baseline["transport"] != current["transport"]:
        raise ConfigSnapshotError(
            "configuration snapshots use different transports: "
            f"{baseline['transport']} != {current['transport']}"
        )
    if baseline["target"] != current["target"] and not allow_target_mismatch:
        raise ConfigSnapshotError(
            "configuration snapshot target does not match the current target: "
            f"{baseline['target']!r} != {current['target']!r}"
        )

    before_by_id = {record["item_id"]: record for record in baseline["objects"]}
    after_by_id = {record["item_id"]: record for record in current["objects"]}
    changes = []
    volatile_changes = []
    read_status_changes = []
    for item_id in range(1, len(CONFIG) + 1):
        before = before_by_id[item_id]
        after = after_by_id[item_id]
        if before.get("status") != after.get("status"):
            read_status_changes.append(_record_change(before, after))
        elif (
            before.get("status") == 0
            and (
                before.get("value_kind"),
                before.get("value"),
            )
            != (
                after.get("value_kind"),
                after.get("value"),
            )
        ):
            target = (
                volatile_changes
                if before.get("volatile") and after.get("volatile")
                else changes
            )
            target.append(_record_change(before, after))
    return {
        "changed": len(changes),
        "volatile_changed": len(volatile_changes),
        "read_status_changed": len(read_status_changes),
        "unchanged": (
            len(CONFIG)
            - len(changes)
            - len(volatile_changes)
            - len(read_status_changes)
        ),
        "target_matches": baseline["target"] == current["target"],
        "changes": changes,
        "volatile_changes": volatile_changes,
        "read_status_changes": read_status_changes,
    }
