"""Read-only review of the next configuration write candidate.

This module evaluates whether a configuration object is a suitable next
candidate for an explicitly authorized write/readback experiment.  It never
authorizes, plans, or sends a device write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import CONFIG, absolute_config_oid

CANDIDATE_REPORT_FORMAT = "kyocera-client-config-write-candidate-report"
CANDIDATE_REPORT_VERSION = 1


@dataclass(frozen=True)
class CandidateDefinition:
    item_id: int
    oid: str
    label: str
    choices: dict[int, str]
    ui_dialog: str
    ui_control: str
    model_offset: str
    mapping_confidence: str
    static_evidence: dict[str, str]
    rationale: str


# Only one next field is recorded here.  Broader candidate lists would invite
# speculation before their UI mapping, type, and device-side effects are
# independently reviewed.
NEXT_WRITE_CANDIDATES: tuple[CandidateDefinition, ...] = (
    CandidateDefinition(
        item_id=50,
        oid="1001.2.1.1.1.14.1",
        label="Quiet mode",
        choices={0: "OFF", 1: "ON"},
        ui_dialog="0x006b",
        ui_control="0x0455",
        model_offset="0x0018",
        mapping_confidence="device_verified",
        static_evidence={
            "ui_initialization": (
                "0x00405ff4 in FUN_00405c10: GetDlgItem(0x455), "
                "BM_SETCHECK(0x00f1)"
            ),
            "ui_value_read": (
                "0x0040b869 in FUN_0040b6f0: BM_GETCHECK(0x00f0), "
                "store boolean at snapshot +0x18"
            ),
            "change_serialization": (
                "0x00411b85 in FUN_00410740 case 0x31: compare model "
                "+0x18, emit OID 1001.2.1.1.1.14.1 as integer 0/1"
            ),
            "serialized_type": "0x69 ('i')",
            "network_writer": "0x00401b57 in FUN_00401b20",
            "usb_writer": (
                "0x0040314f in FUN_00402ec0: relative prefix '1.'"
            ),
            "reset_request_set_by_item50": "false",
            "device_validation": (
                "2026-11-01 MA2000w SNMPv2c SET OFF -> ON returned Integer "
                "1 and read back 1; SET OFF returned Integer 0 and read back "
                "0; full configuration comparison had no persistent or "
                "read-status changes."
            ),
        },
        rationale=(
            "The checked Client Tool path connects checkbox 0x0455 to "
            "snapshot offset 0x0018, compares it in diff case 0x31, and "
            "serializes OID 1001.2.1.1.1.14.1 as an integer 0/1.  The "
            "network and USB writers consume the same record.  MA2000w "
            "SNMPv2c write/readback and rollback have now been verified."
        ),
    ),
)

_CONFIG_BY_ID = {obj.item_id: obj for obj in CONFIG}


class ConfigCandidateError(ValueError):
    """Raised when a candidate report cannot be built safely."""


def _append_once(blockers: list[str], value: str) -> None:
    if value not in blockers:
        blockers.append(value)


def build_config_candidate_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a read-only assessment of the next write candidate.

    ``current_read_valid`` means the observed object has the expected integer
    type and a documented enum value.  It does not mean that writing is safe
    or authorized.  Every candidate keeps ``write.allowed`` false and carries
    the remaining evidence and authorization blockers.
    """
    if not isinstance(snapshot, dict):
        raise ConfigCandidateError("configuration snapshot must be an object")
    objects = snapshot.get("objects")
    if not isinstance(objects, list):
        raise ConfigCandidateError("configuration snapshot has no object list")
    by_id: dict[int, dict[str, Any]] = {}
    for record in objects:
        if not isinstance(record, dict) or not isinstance(
            record.get("item_id"), int
        ):
            raise ConfigCandidateError(
                "configuration snapshot contains an invalid object record"
            )
        by_id[record["item_id"]] = record
    if len(by_id) != len(CONFIG):
        raise ConfigCandidateError(
            f"expected {len(CONFIG)} configuration objects, got {len(by_id)}"
        )

    reports: list[dict[str, Any]] = []
    for candidate in NEXT_WRITE_CANDIDATES:
        expected = _CONFIG_BY_ID.get(candidate.item_id)
        if expected is None or expected.oid != candidate.oid:
            raise ConfigCandidateError(
                f"candidate item {candidate.item_id} does not match the "
                "configuration catalog"
            )
        if expected.type_code != 0:
            raise ConfigCandidateError(
                f"candidate item {candidate.item_id} is not catalogued as integer"
            )

        record = by_id.get(candidate.item_id)
        if record is None:
            raise ConfigCandidateError(
                f"configuration snapshot has no item {candidate.item_id}"
            )
        if record.get("oid") != candidate.oid:
            raise ConfigCandidateError(
                f"candidate item {candidate.item_id} OID does not match "
                "the configuration catalog"
            )
        read_blockers: list[str] = []
        if record.get("status") != 0:
            _append_once(read_blockers, "current_object_not_readable")
        if record.get("type_code") != expected.type_code:
            _append_once(read_blockers, "unexpected_catalog_type")
        if record.get("value_kind") != "integer":
            _append_once(read_blockers, "current_value_not_integer")
        value = record.get("value")
        if record.get("status") == 0 and value not in candidate.choices:
            _append_once(read_blockers, "unexpected_current_value")

        write_blockers = list(read_blockers)
        _append_once(
            write_blockers,
            "device_failure_recovery_unverified",
        )
        _append_once(write_blockers, "explicit_user_authorization_required")

        reports.append(
            {
                "item_id": candidate.item_id,
                "label": candidate.label,
                "oid": expected.oid,
                "absolute_oid": absolute_config_oid(expected.oid),
                "pjl_object": expected.pjl_object,
                "value_type": "integer",
                "choices": [
                    {"value": choice_value, "label": choice_label}
                    for choice_value, choice_label in candidate.choices.items()
                ],
                "observed": {
                    "status": record.get("status"),
                    "value": value,
                    "display": record.get("display"),
                    "raw_value": record.get("raw_value"),
                },
                "evidence": {
                    "ui_dialog": candidate.ui_dialog,
                    "ui_control": candidate.ui_control,
                    "model_offset": candidate.model_offset,
                    "mapping_confidence": candidate.mapping_confidence,
                    "static_data_flow": candidate.static_evidence,
                    "source": (
                        "docs/reverse-engineering/data/"
                        "clienttool-control-oids.tsv"
                    ),
                    "rationale": candidate.rationale,
                },
                "review": {
                    "current_read_valid": not read_blockers,
                    "read_blockers": read_blockers,
                },
                "write": {
                    "allowed": False,
                    "blockers": write_blockers,
                    "requires_user_authorization": True,
                },
            }
        )

    ready = next(
        (
            report
            for report in reports
            if report["review"]["current_read_valid"]
        ),
        None,
    )
    return {
        "format": CANDIDATE_REPORT_FORMAT,
        "version": CANDIDATE_REPORT_VERSION,
        "read_only": True,
        "target": snapshot.get("target"),
        "transport": snapshot.get("transport"),
        "read": snapshot.get("read"),
        "total": snapshot.get("total"),
        "candidates": reports,
        "recommendation": {
            "item_id": ready["item_id"] if ready is not None else None,
            "status": (
                "device_verified_explicit_authorization_required"
                if ready is not None
                else "blocked"
            ),
            "note": (
                "This report sends no write command and does not authorize "
                "a device experiment."
            ),
        },
    }
