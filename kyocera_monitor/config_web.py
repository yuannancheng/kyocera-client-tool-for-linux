"""Web/GUI orchestration for printer configuration reads and reviewed writes."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .config import CONFIG, CONFIG_KNOWN
from .config_edit import (
    EDITABLE_BY_ID,
    display_edit_value,
    editable_value_allowed,
)
from .config_snapshot import (
    ConfigSnapshotError,
    build_config_snapshot,
    compare_config_snapshots,
    load_config_snapshot,
    save_config_snapshot,
)

ConfigReader = Callable[[str], list[dict]]
IntegerWriter = Callable[[str, str, int], object]

STATUS_ITEMS = (1, 2, 3, 49, 50, 52, 84, 85, 142, 143, 144, 145, 146, 147)


class ConfigWorkbenchError(RuntimeError):
    """Raised when a guarded configuration operation cannot proceed."""


def default_baseline_directory() -> Path:
    import os

    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".config"
    return base / "kyocera-monitor" / "baselines"


def baseline_filename(host: str) -> str:
    digest = hashlib.sha256(host.encode("utf-8")).hexdigest()
    return f"{digest}.json"


def _record_view(record: dict) -> dict[str, object]:
    sensitive = bool(record.get("sensitive"))
    display = record.get("display")
    if sensitive:
        display = "<redacted>"
    known = CONFIG_KNOWN.get(record["oid"], {})
    return {
        "item_id": record["item_id"],
        "label": (
            record.get("label")
            or known.get("label")
            or record.get("vendor_name")
            or record.get("pjl_object")
            or record["oid"]
        ),
        "oid": record["oid"],
        "absolute_oid": record["absolute_oid"],
        "status": record.get("status"),
        "display": display,
        "unit": record.get("unit") or known.get("unit"),
        "confidence": record.get("confidence") or known.get("confidence"),
        "sensitive": sensitive,
        "volatile": bool(record.get("volatile")),
        "readable": record.get("status") == 0,
    }


def _editable_view(record: dict) -> dict[str, object] | None:
    setting = EDITABLE_BY_ID.get(record["item_id"])
    if setting is None:
        return None
    value = record.get("value")
    readable = (
        record.get("status") == 0
        and isinstance(value, int)
        and not isinstance(value, bool)
        and (
            record.get("value_kind") in (None, "integer")
            or "value_kind" not in record
        )
    )
    return {
        "item_id": setting.item_id,
        "label": setting.label,
        "description": setting.description,
        "oid": record["absolute_oid"],
        "readable": readable,
        "current_value": value if readable else None,
        "current_display": (
            display_edit_value(setting, value) if readable else None
        ),
        "scale": setting.scale,
        "unit": setting.unit,
        "choices": [
            {"value": choice, "label": label}
            for choice, label in setting.choices
        ],
    }


class ConfigWorkbench:
    """Read configuration, manage baselines, and apply reviewed integer edits."""

    def __init__(
        self,
        reader: ConfigReader,
        *,
        writer: IntegerWriter | None = None,
        baseline_directory: Path | None = None,
        transport: str = "snmp",
    ):
        if transport not in {"pjl", "snmp"}:
            raise ValueError(f"unsupported configuration transport: {transport}")
        self._reader = reader
        self._writer = writer
        self._baseline_directory = baseline_directory or default_baseline_directory()
        self._transport = transport
        self._lock = threading.Lock()

    @property
    def transport(self) -> str:
        return self._transport

    def _read_snapshot(self, host: str) -> dict:
        try:
            records = self._reader(host)
            return build_config_snapshot(
                records,
                transport=self._transport,
                target=host,
            )
        except ConfigSnapshotError:
            raise
        except Exception as exc:
            raise ConfigWorkbenchError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def baseline_path(self, host: str) -> Path:
        return self._baseline_directory / baseline_filename(host)

    def baseline_info(self, host: str) -> dict[str, object]:
        path = self.baseline_path(host)
        if not path.is_file():
            return {"available": False}
        try:
            baseline = load_config_snapshot(path)
        except ConfigSnapshotError as exc:
            return {"available": False, "error": str(exc)}
        return {
            "available": True,
            "created_at": baseline["created_at"],
            "target": baseline["target"],
            "transport": baseline["transport"],
            "read": baseline["read"],
            "total": baseline["total"],
            "checksum": baseline["checksum"]["canonical_json"],
        }

    def overview(self, host: str) -> dict[str, object]:
        with self._lock:
            snapshot = self._read_snapshot(host)
        by_id = {
            record["item_id"]: _record_view(record)
            for record in snapshot["objects"]
        }
        return {
            "host": host,
            "transport": self._transport,
            "created_at": snapshot["created_at"],
            "read": snapshot["read"],
            "total": snapshot["total"],
            "checksum": snapshot["checksum"]["canonical_json"],
            "baseline": self.baseline_info(host),
            "editing": {
                "available": self._writer is not None,
                "items": [
                    item
                    for record in snapshot["objects"]
                    if (item := _editable_view(record)) is not None
                ],
            },
            "objects": [
                _record_view(record) for record in snapshot["objects"]
            ],
            "status_objects": [by_id[item_id] for item_id in STATUS_ITEMS],
        }

    def save_baseline(self, host: str) -> dict[str, object]:
        with self._lock:
            snapshot = self._read_snapshot(host)
            self._baseline_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = save_config_snapshot(
                self.baseline_path(host),
                snapshot,
                overwrite=True,
            )
        return {"saved": True, "baseline": self.baseline_info(host), "path": str(path)}

    def compare_baseline(self, host: str) -> dict[str, object]:
        path = self.baseline_path(host)
        with self._lock:
            if not path.is_file():
                raise ConfigWorkbenchError("configuration baseline does not exist")
            baseline = load_config_snapshot(path)
            current = self._read_snapshot(host)
            comparison = compare_config_snapshots(baseline, current)
        return {
            "host": host,
            "baseline": self.baseline_info(host),
            "current": {
                "created_at": current["created_at"],
                "read": current["read"],
                "total": current["total"],
                "checksum": current["checksum"]["canonical_json"],
            },
            "comparison": comparison,
        }

    def apply_integer(
        self,
        host: str,
        item_id: object,
        value: object,
        expected_value: object,
        *,
        readback_timeout: float = 4.0,
        readback_interval: float = 0.25,
    ) -> dict[str, Any]:
        """Apply one reviewed integer setting and prove the device readback.

        The caller must submit the value it observed.  A different current
        value fails closed so two open pages cannot silently overwrite each
        other.  A failed write or readback attempts to restore the observed
        value and reports both the requested and recovery observations.
        """

        if self._writer is None:
            raise ConfigWorkbenchError(
                "device configuration writes are unavailable for this connection"
            )
        if isinstance(item_id, bool) or not isinstance(item_id, int):
            raise ConfigWorkbenchError("configuration item_id must be an integer")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigWorkbenchError("configuration value must be an integer")
        if isinstance(expected_value, bool) or not isinstance(expected_value, int):
            raise ConfigWorkbenchError(
                "expected_value must be the integer previously observed"
            )
        setting = EDITABLE_BY_ID.get(item_id)
        if setting is None:
            raise ConfigWorkbenchError(
                f"item {item_id} is not in the reviewed editable property set"
            )
        if not editable_value_allowed(setting, value):
            allowed = ", ".join(
                f"{label}={number}" for number, label in setting.choices
            )
            raise ConfigWorkbenchError(
                f"item {item_id} accepts only {allowed}; got {value}"
            )
        with self._lock:
            current = self._read_snapshot(host)
            record = next(
                item
                for item in current["objects"]
                if item["item_id"] == item_id
            )
            catalog_type = next(
                item.type_code for item in CONFIG if item.item_id == item_id
            )
            if (
                record.get("status") != 0
                or catalog_type != 0
                or not isinstance(record.get("value"), int)
                or isinstance(record.get("value"), bool)
            ):
                raise ConfigWorkbenchError(
                    f"item {item_id} is not readable as an integer"
                )
            before = record.get("value")
            if before != expected_value:
                raise ConfigWorkbenchError(
                    "configuration changed after it was displayed; read it again "
                    f"(expected {expected_value}, found {before})"
                )
            if value == before:
                raise ConfigWorkbenchError(
                    "requested value already equals current value"
                )

            oid = record["absolute_oid"]
            result: dict[str, Any] = {
                "status": "failed",
                "host": host,
                "item_id": item_id,
                "label": setting.label,
                "oid": oid,
                "before": before,
                "before_display": display_edit_value(setting, before),
                "requested": value,
                "observed": None,
                "observed_display": None,
                "readback": False,
                "rollback": {
                    "attempted": False,
                    "ok": False,
                    "observed": None,
                    "error": None,
                },
            }
            try:
                self._writer(host, oid, value)
                observed, error = self._wait_for_item(
                    host,
                    item_id,
                    value,
                    timeout=readback_timeout,
                    interval=readback_interval,
                )
                result["observed"] = observed
                if observed is not None:
                    result["observed_display"] = display_edit_value(
                        setting,
                        observed,
                    )
                result["readback"] = observed == value
                result["readback_error"] = error
                if observed != value:
                    raise ConfigWorkbenchError(
                        f"device did not read back {value}; observed {observed}"
                    )
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
                result["rollback"]["attempted"] = True
                try:
                    self._writer(host, oid, expected_value)
                    observed, rollback_error = self._wait_for_item(
                        host,
                        item_id,
                        expected_value,
                        timeout=readback_timeout,
                        interval=readback_interval,
                    )
                    result["rollback"]["observed"] = observed
                    result["rollback"]["ok"] = observed == expected_value
                    result["rollback"]["error"] = rollback_error
                except Exception as rollback_exc:
                    result["rollback"]["error"] = (
                        f"{type(rollback_exc).__name__}: {rollback_exc}"
                    )
                if result["rollback"]["ok"]:
                    result["status"] = "rolled_back"
                else:
                    result["status"] = "rollback_failed"
                raise ConfigWorkbenchError(
                    result["error"]
                    if result["rollback"]["ok"]
                    else (
                        f"{result['error']}; rollback failed: "
                        f"{result['rollback']['error']}"
                    )
                ) from exc

            result["status"] = "applied"
            return result

    def _wait_for_item(
        self,
        host: str,
        item_id: int,
        expected: int,
        *,
        timeout: float,
        interval: float,
    ) -> tuple[int | None, str | None]:
        deadline = time.monotonic() + max(timeout, 0)
        observed: int | None = None
        last_error: str | None = None
        while True:
            try:
                snapshot = self._read_snapshot(host)
                record = next(
                    item
                    for item in snapshot["objects"]
                    if item["item_id"] == item_id
                )
                value = record.get("value")
                if record.get("status") == 0 and isinstance(value, int):
                    observed = value
                    last_error = None
                    if observed == expected:
                        return observed, None
                else:
                    last_error = "configuration item is not readable as an integer"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return (
                    observed,
                    last_error
                    or f"expected {expected}, got {observed}",
                )
            time.sleep(min(max(interval, 0.01), remaining))

__all__ = [
    "ConfigWorkbench",
    "ConfigWorkbenchError",
    "STATUS_ITEMS",
    "baseline_filename",
]
