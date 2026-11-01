"""Web-facing orchestration for guarded printer configuration operations."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Callable

from .config import CONFIG_KNOWN
from .config_snapshot import (
    ConfigSnapshotError,
    build_config_snapshot,
    compare_config_snapshots,
    load_config_snapshot,
    save_config_snapshot,
)
from .config_write_executor import execute_authorized_config_experiment
from .config_write_plan import (
    SAFE_INTEGER_SETTINGS,
    ConfigWritePlanError,
    build_config_write_plan,
)
from .snmp import SnmpClient

ConfigReader = Callable[[str], list[dict]]
ClientFactory = Callable[[str], SnmpClient]

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
    write_policy = (
        "reversible_experiment"
        if record["item_id"] in SAFE_INTEGER_SETTINGS
        else "read_only"
    )
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
        "write_policy": write_policy,
    }


class ConfigWorkbench:
    """Serialize configuration reads and guard the two verified experiments."""

    def __init__(
        self,
        reader: ConfigReader,
        *,
        client_factory: ClientFactory | None = None,
        baseline_directory: Path | None = None,
        transport: str = "snmp",
    ):
        if transport not in {"pjl", "snmp"}:
            raise ValueError(f"unsupported configuration transport: {transport}")
        self._reader = reader
        self._client_factory = client_factory
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
        candidates = []
        for item_id, candidate in sorted(SAFE_INTEGER_SETTINGS.items()):
            current = by_id[item_id]
            candidates.append(
                {
                    "item_id": item_id,
                    "label": current["label"],
                    "choices": [
                        {"value": value, "label": label}
                        for value, label in candidate.choices.items()
                    ],
                    "authorized_transition": (
                        {
                            "from": candidate.authorized_transition[0],
                            "to": candidate.authorized_transition[1],
                        }
                        if candidate.authorized_transition
                        else None
                    ),
                    "execution_supported": bool(candidate.authorized_transition),
                    "current": current,
                }
            )
        return {
            "host": host,
            "transport": self._transport,
            "created_at": snapshot["created_at"],
            "read": snapshot["read"],
            "total": snapshot["total"],
            "checksum": snapshot["checksum"]["canonical_json"],
            "baseline": self.baseline_info(host),
            "objects": [
                _record_view(record) for record in snapshot["objects"]
            ],
            "status_objects": [by_id[item_id] for item_id in STATUS_ITEMS],
            "candidates": candidates,
            "write_execution_available": self._client_factory is not None,
            "warning": (
                "Only item 2 Auto error clear and item 50 Quiet mode expose "
                "the verified OFF -> ON -> OFF rollback experiment. All other "
                "objects remain read-only."
            ),
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

    def plan(self, host: str, item_id: int, value: str) -> dict[str, object]:
        assignment = f"{item_id}={value}"
        path = self.baseline_path(host)
        with self._lock:
            if not path.is_file():
                raise ConfigWorkbenchError("configuration baseline does not exist")
            baseline = load_config_snapshot(path)
            current = self._read_snapshot(host)
            plan = build_config_write_plan(baseline, current, assignment)
        return {
            "host": host,
            "plan": plan,
            "write_execution_available": self._client_factory is not None,
        }

    def apply(
        self,
        host: str,
        item_id: int,
        value: str,
        confirmation_token: str,
    ) -> dict[str, object]:
        if self._client_factory is None:
            raise ConfigWorkbenchError(
                "configuration writes are unavailable for this connection"
            )
        assignment = f"{item_id}={value}"
        path = self.baseline_path(host)
        with self._lock:
            if not path.is_file():
                raise ConfigWorkbenchError("configuration baseline does not exist")
            baseline = load_config_snapshot(path)
            current = self._read_snapshot(host)
            plan = build_config_write_plan(baseline, current, assignment)
            client = self._client_factory(host)
            execution = execute_authorized_config_experiment(
                client,
                plan,
                confirmation_token,
            )
        return {"host": host, "plan": plan, "execution": execution}


__all__ = [
    "ConfigWorkbench",
    "ConfigWorkbenchError",
    "ConfigWritePlanError",
    "STATUS_ITEMS",
    "baseline_filename",
]
