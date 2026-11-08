"""Web/GUI orchestration for printer configuration reads and reviewed writes."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import CONFIG, CONFIG_KNOWN, absolute_config_oid
from .config_edit import (
    EDITABLE_BY_ID,
    display_edit_value,
    editable_value_allowed,
)
from .config_snapshot import (
    SENSITIVE_ITEM_IDS,
    VOLATILE_ITEM_IDS,
    ConfigSnapshotError,
    build_config_snapshot,
    compare_config_snapshots,
    load_config_snapshot,
    save_config_snapshot,
)

ConfigReader = Callable[[str], list[dict]]
ScopedConfigReader = Callable[[str, tuple[int, ...]], list[dict]]
IntegerWriter = Callable[[str, str, int], object]
TransportSelector = str | Callable[[str], str]
WriterAvailability = Callable[[str], bool]

STATUS_ITEMS = (1, 2, 3, 49, 50, 52, 84, 85, 142, 143, 144, 145, 146, 147)


@dataclass(frozen=True)
class ConfigSection:
    """One settings page modelled after the official Client Tool dialogs."""

    key: str
    label: str
    description: str
    item_ids: tuple[int, ...]


CONFIG_SECTIONS: tuple[ConfigSection, ...] = (
    ConfigSection(
        key="general",
        label="设备默认值",
        description=(
            "睡眠、错误清除、打印浓度、送纸与常用默认值；"
            "对应官方主设置页。"
        ),
        item_ids=(
            *range(1, 11),
            *range(49, 54),
            83,
            87,
        ),
    ),
    ConfigSection(
        key="paper",
        label="纸张与介质",
        description="自定义纸张名称、重量、类型和纸路设置。",
        item_ids=tuple(range(11, 49)),
    ),
    ConfigSection(
        key="communication",
        label="通信设置",
        description=(
            "主机名、IPv4、DHCP、LPD/Raw/WSD 和 SNMP 社区；"
            "对应官方 Communication 页。"
        ),
        item_ids=tuple(range(54, 71)),
    ),
    ConfigSection(
        key="snmp_traps",
        label="SNMP Trap",
        description="认证 Trap、两个收件人及其事件通知；对应官方 Trap 页。",
        item_ids=tuple(range(71, 79)),
    ),
    ConfigSection(
        key="panel",
        label="面板与扫描",
        description=(
            "面板语言、默认画面、自动清除和扫描纸张尺寸；"
            "对应官方 Panel options 与扫描默认值。"
        ),
        item_ids=(
            *range(79, 83),
            *range(84, 87),
            *range(88, 94),
        ),
    ),
    ConfigSection(
        key="fax",
        label="传真设置",
        description="扬声器、报告、接收模式、转发及通信参数。",
        item_ids=tuple(range(94, 142)),
    ),
    ConfigSection(
        key="wifi",
        label="Wi‑Fi",
        description="连接状态、SSID、安全模式、信号与信道；对应官方 Wi‑Fi 页。",
        item_ids=tuple(range(142, 148)),
    ),
)

CONFIG_SECTIONS_BY_KEY = {section.key: section for section in CONFIG_SECTIONS}


class ConfigCategoryError(ValueError):
    """Raised when a requested configuration section does not exist."""


def configuration_section(key: object) -> ConfigSection:
    """Resolve a stable configuration section key."""

    if not isinstance(key, str) or key not in CONFIG_SECTIONS_BY_KEY:
        valid = ", ".join(section.key for section in CONFIG_SECTIONS)
        raise ConfigCategoryError(
            f"unknown configuration category {key!r}; expected one of {valid}"
        )
    return CONFIG_SECTIONS_BY_KEY[key]


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
    item_id = record["item_id"]
    oid = record["oid"]
    absolute_oid = (
        record.get("absolute_oid") or absolute_config_oid(oid)
    )
    sensitive = (
        bool(record.get("sensitive")) or item_id in SENSITIVE_ITEM_IDS
    )
    display = record.get("display")
    if sensitive:
        display = "<redacted>"
    known = CONFIG_KNOWN.get(oid, {})
    return {
        "item_id": item_id,
        "label": (
            record.get("label")
            or known.get("label")
            or record.get("vendor_name")
            or record.get("pjl_object")
            or oid
        ),
        "oid": oid,
        "absolute_oid": absolute_oid,
        "status": record.get("status"),
        "display": display,
        "unit": record.get("unit") or known.get("unit"),
        "confidence": record.get("confidence") or known.get("confidence"),
        "sensitive": sensitive,
        "volatile": (
            bool(record.get("volatile")) or item_id in VOLATILE_ITEM_IDS
        ),
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
        "oid": (
            record.get("absolute_oid")
            or absolute_config_oid(record["oid"])
        ),
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
        scoped_reader: ScopedConfigReader | None = None,
        writer: IntegerWriter | None = None,
        writer_available: WriterAvailability | None = None,
        baseline_directory: Path | None = None,
        transport: TransportSelector = "snmp",
    ):
        if isinstance(transport, str) and transport not in {"pjl", "snmp"}:
            raise ValueError(f"unsupported configuration transport: {transport}")
        if not isinstance(transport, str) and not callable(transport):
            raise ValueError("configuration transport must be a selector")
        if writer_available is not None and not callable(writer_available):
            raise ValueError("writer_available must be callable")
        self._reader = reader
        self._scoped_reader = scoped_reader
        self._writer = writer
        self._writer_available = writer_available
        self._baseline_directory = baseline_directory or default_baseline_directory()
        self._transport = transport
        self._lock = threading.Lock()

    @property
    def transport(self) -> str:
        return self._transport if isinstance(self._transport, str) else "auto"

    def _transport_for(self, host: str) -> str:
        transport = (
            self._transport(host)
            if callable(self._transport)
            else self._transport
        )
        if transport not in {"pjl", "snmp"}:
            raise ConfigWorkbenchError(
                f"unsupported configuration transport: {transport!r}"
            )
        return transport

    def _writes_available(self, host: str) -> bool:
        if self._writer is None:
            return False
        if self._writer_available is None:
            return True
        return bool(self._writer_available(host))

    def _read_snapshot(self, host: str) -> dict:
        try:
            records = self._read_records(host)
            return build_config_snapshot(
                records,
                transport=self._transport_for(host),
                target=host,
            )
        except ConfigSnapshotError:
            raise
        except ConfigWorkbenchError:
            raise
        except Exception as exc:
            raise ConfigWorkbenchError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _read_records(
        self,
        host: str,
        item_ids: tuple[int, ...] | None = None,
    ) -> list[dict]:
        """Read all items, or only one official settings-page scope."""

        try:
            if item_ids is None:
                return self._reader(host)
            if self._scoped_reader is not None:
                records = self._scoped_reader(host, item_ids)
            else:
                records = self._reader(host)
            by_id = {record.get("item_id"): record for record in records}
            missing = [
                item_id for item_id in item_ids if item_id not in by_id
            ]
            if missing:
                raise ConfigWorkbenchError(
                    "configuration read omitted requested items: "
                    + ", ".join(str(item_id) for item_id in missing)
                )
            return [by_id[item_id] for item_id in item_ids]
        except ConfigWorkbenchError:
            raise
        except Exception as exc:
            raise ConfigWorkbenchError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def category_catalog(self) -> list[dict[str, object]]:
        """Return the stable navigation metadata without contacting a device."""

        editable = set(EDITABLE_BY_ID)
        return [
            {
                "key": section.key,
                "label": section.label,
                "description": section.description,
                "item_count": len(section.item_ids),
                "editable_count": sum(
                    item_id in editable for item_id in section.item_ids
                ),
            }
            for section in CONFIG_SECTIONS
        ]

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

    def overview(
        self,
        host: str,
        *,
        category: str = "general",
    ) -> dict[str, object]:
        section = configuration_section(category)
        with self._lock:
            records = self._read_records(host, section.item_ids)
        by_id = {
            record["item_id"]: _record_view(record)
            for record in records
        }
        return {
            "host": host,
            "transport": self._transport_for(host),
            "category": {
                "key": section.key,
                "label": section.label,
                "description": section.description,
                "item_count": len(section.item_ids),
            },
            "categories": self.category_catalog(),
            "read": sum(record.get("status") == 0 for record in records),
            "total": len(records),
            "full_total": len(CONFIG),
            "baseline": self.baseline_info(host),
            "editing": {
                "available": self._writes_available(host),
                "items": [
                    item
                    for record in records
                    if (item := _editable_view(record)) is not None
                ],
            },
            "objects": [
                _record_view(record) for record in records
            ],
            "status_objects": [
                by_id[item_id]
                for item_id in STATUS_ITEMS
                if item_id in by_id
            ],
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

        if not self._writes_available(host):
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
            current = self._read_records(host, (item_id,))
            record = next(
                (item for item in current if item["item_id"] == item_id),
                None,
            )
            if record is None:
                raise ConfigWorkbenchError(
                    f"configuration item {item_id} was not returned"
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

            oid = (
                record.get("absolute_oid")
                or absolute_config_oid(record["oid"])
            )
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
                records = self._read_records(host, (item_id,))
                record = next(
                    (item for item in records if item["item_id"] == item_id),
                    None,
                )
                if record is None:
                    raise ConfigWorkbenchError(
                        f"configuration item {item_id} was not returned"
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
    "CONFIG_SECTIONS",
    "CONFIG_SECTIONS_BY_KEY",
    "ConfigCategoryError",
    "ConfigSection",
    "ConfigWorkbench",
    "ConfigWorkbenchError",
    "STATUS_ITEMS",
    "baseline_filename",
    "configuration_section",
]
