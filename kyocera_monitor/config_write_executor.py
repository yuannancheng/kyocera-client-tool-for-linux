"""Execute explicitly authorized single-field configuration experiments.

The executors support only item 2 Auto error clear and item 50 Quiet mode,
each changing from OFF to ON and rolling back to OFF over SNMPv2c. Every
forward attempt is followed by a rollback attempt and a same-OID readback,
including when the forward write or verification fails.
"""

from __future__ import annotations

import hmac
import time
from typing import Any

from .config_write_plan import (
    AUTHORIZATION_SCOPE,
    QUIET_MODE_AUTHORIZATION_SCOPE,
    WRITE_PLAN_FORMAT,
    WRITE_PLAN_VERSION,
)
from .snmp import BerError, SnmpClient


class ConfigWriteExecutionError(ValueError):
    """Raised before the first write when execution prerequisites fail."""


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _confirmation_value(token: str) -> str:
    value = token.strip()
    if value.startswith("sha256:"):
        value = value[len("sha256:") :]
    return value


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


def _validate_plan(
    client: SnmpClient,
    plan: dict[str, Any],
    confirmation_token: str,
    *,
    authorization_scope: str,
    item_id: int,
    label: str,
) -> None:
    if plan.get("format") != WRITE_PLAN_FORMAT:
        raise ConfigWriteExecutionError("unrecognized write plan format")
    if plan.get("version") != WRITE_PLAN_VERSION:
        raise ConfigWriteExecutionError("unsupported write plan version")
    if plan["execution"].get("authorization_scope") != authorization_scope:
        raise ConfigWriteExecutionError("unexpected write authorization scope")
    if plan["transport"] != "snmp":
        raise ConfigWriteExecutionError("this executor supports SNMP only")
    if getattr(client, "host", None) != plan["target"]:
        raise ConfigWriteExecutionError("SNMP client target does not match plan")
    if not plan["review"]["ready_for_executor_implementation"]:
        raise ConfigWriteExecutionError("write plan has blocking preconditions")
    if not plan["execution"]["allowed"]:
        raise ConfigWriteExecutionError("write plan execution is not allowed")
    expected_token = plan["confirmation"]["token"]
    if not hmac.compare_digest(expected_token, _confirmation_value(confirmation_token)):
        raise ConfigWriteExecutionError("confirmation token does not match plan")
    if plan["object"]["item_id"] != item_id:
        raise ConfigWriteExecutionError(
            f"only {label} is authorized by this executor"
        )
    if (
        plan["before"]["value"] != 0
        or plan["current"]["value"] != 0
        or plan["requested"]["value"] != 1
        or plan["rollback"]["value"] != 0
    ):
        raise ConfigWriteExecutionError(
            f"authorized transition must be {label} OFF -> ON -> OFF"
        )


def _execute_off_on_off_experiment(
    client: SnmpClient,
    plan: dict[str, Any],
    confirmation_token: str,
    *,
    authorization_scope: str,
    item_id: int,
    label: str,
    readback_timeout: float,
    readback_interval: float,
) -> dict[str, Any]:
    _validate_plan(
        client,
        plan,
        confirmation_token,
        authorization_scope=authorization_scope,
        item_id=item_id,
        label=label,
    )
    oid = plan["object"]["absolute_oid"]
    before_value = _read_integer(client, oid)
    if before_value != 0:
        raise ConfigWriteExecutionError(
            f"pre-write value changed to {before_value}; expected OFF"
        )

    result: dict[str, Any] = {
        "status": "rollback_failed",
        "target": plan["target"],
        "transport": "snmp",
        "authorization_scope": authorization_scope,
        "item_id": item_id,
        "label": label,
        "oid": oid,
        "preflight_value": before_value,
        "requested_value": 1,
        "rollback_value": 0,
        "set_on": {"attempted": True, "ok": False, "error": None},
        "verify_on": {"expected": 1, "observed": None, "ok": False, "error": None},
        "set_off": {"attempted": True, "ok": False, "error": None},
        "verify_off": {"expected": 0, "observed": None, "ok": False, "error": None},
    }

    try:
        try:
            client.set_integer(oid, 1)
            result["set_on"]["ok"] = True
        except (BerError, OSError, TimeoutError, ValueError) as exc:
            result["set_on"]["error"] = _error_text(exc)

        on_value, on_error = _wait_for_value(
            client,
            oid,
            1,
            timeout=readback_timeout,
            interval=readback_interval,
        )
        result["verify_on"] = {
            "expected": 1,
            "observed": on_value,
            "ok": on_value == 1,
            "error": on_error,
        }
    finally:
        try:
            client.set_integer(oid, 0)
            result["set_off"]["ok"] = True
        except (BerError, OSError, TimeoutError, ValueError) as exc:
            result["set_off"]["error"] = _error_text(exc)

        off_value, off_error = _wait_for_value(
            client,
            oid,
            0,
            timeout=readback_timeout,
            interval=readback_interval,
        )
        result["verify_off"] = {
            "expected": 0,
            "observed": off_value,
            "ok": off_value == 0,
            "error": off_error,
        }

    forward_ok = result["set_on"]["ok"] and result["verify_on"]["ok"]
    rollback_ok = result["set_off"]["ok"] and result["verify_off"]["ok"]
    if forward_ok and rollback_ok:
        result["status"] = "success"
    elif rollback_ok:
        result["status"] = "rolled_back"
    else:
        result["status"] = "rollback_failed"
    return result


def execute_auto_error_clear_experiment(
    client: SnmpClient,
    plan: dict[str, Any],
    confirmation_token: str,
    *,
    readback_timeout: float = 4.0,
    readback_interval: float = 0.25,
) -> dict[str, Any]:
    """Run the authorized Auto error clear OFF -> ON -> OFF experiment."""
    return _execute_off_on_off_experiment(
        client,
        plan,
        confirmation_token,
        authorization_scope=AUTHORIZATION_SCOPE,
        item_id=2,
        label="Auto error clear",
        readback_timeout=readback_timeout,
        readback_interval=readback_interval,
    )


def execute_quiet_mode_experiment(
    client: SnmpClient,
    plan: dict[str, Any],
    confirmation_token: str,
    *,
    readback_timeout: float = 4.0,
    readback_interval: float = 0.25,
) -> dict[str, Any]:
    """Run the authorized Quiet mode OFF -> ON -> OFF experiment."""
    return _execute_off_on_off_experiment(
        client,
        plan,
        confirmation_token,
        authorization_scope=QUIET_MODE_AUTHORIZATION_SCOPE,
        item_id=50,
        label="Quiet mode",
        readback_timeout=readback_timeout,
        readback_interval=readback_interval,
    )


def execute_authorized_config_experiment(
    client: SnmpClient,
    plan: dict[str, Any],
    confirmation_token: str,
    *,
    readback_timeout: float = 4.0,
    readback_interval: float = 0.25,
) -> dict[str, Any]:
    """Dispatch only the exact single-field experiments implemented above."""
    scope = plan.get("execution", {}).get("authorization_scope")
    if scope == AUTHORIZATION_SCOPE:
        return execute_auto_error_clear_experiment(
            client,
            plan,
            confirmation_token,
            readback_timeout=readback_timeout,
            readback_interval=readback_interval,
        )
    if scope == QUIET_MODE_AUTHORIZATION_SCOPE:
        return execute_quiet_mode_experiment(
            client,
            plan,
            confirmation_token,
            readback_timeout=readback_timeout,
            readback_interval=readback_interval,
        )
    raise ConfigWriteExecutionError("unexpected write authorization scope")
