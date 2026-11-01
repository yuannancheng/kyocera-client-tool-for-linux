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
        mapping_confidence="inferred",
        rationale=(
            "The checked Client Tool mapping connects the main-dialog "
            "checkbox 0x0455 and model offset 0x0018 to item 50.  The "
            "reviewed evidence does not connect this object to an IP, "
            "Wi-Fi, or SNMP credential setting, but that classification "
            "remains inferred until a write/readback experiment is run."
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
        if candidate.mapping_confidence != "verified":
            _append_once(write_blockers, "field_mapping_inferred")
        _append_once(write_blockers, "same_oid_write_readback_unverified")
        _append_once(write_blockers, "restart_and_failure_side_effects_unknown")
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
                "ready_for_authorization_review"
                if ready is not None
                else "blocked"
            ),
            "note": (
                "This report sends no write command and does not authorize "
                "a device experiment."
            ),
        },
    }
