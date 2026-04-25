from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso

from .vault_promotion_request import validate_vault_promotion_request


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
EFFORT_AWARE_GARDENER_WORTHINESS_SCHEMA_PATH = (
    CONTRACTS_ROOT / "effort_aware_gardener_worthiness.v1.schema.json"
)

EFFORT_ORDER = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "xhigh": 4,
}
EFFORT_STATUS_VALUES = {"verified", "declared", "downgraded", "unavailable", "unknown"}


@lru_cache(maxsize=1)
def load_effort_aware_gardener_worthiness_schema() -> dict[str, Any]:
    return json.loads(EFFORT_AWARE_GARDENER_WORTHINESS_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_effort_aware_gardener_worthiness(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_effort_aware_gardener_worthiness_schema(),
    )


def _normalize_effort_level(value: Any) -> str:
    token = str(value or "").strip().lower().replace("-", "").replace("_", "")
    if token in {"xhigh", "extrahigh"}:
        return "xhigh"
    if token in EFFORT_ORDER and token != "unknown":
        return token
    return "unknown"


def _normalize_effort_status(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in EFFORT_STATUS_VALUES:
        return token
    return "unknown"


def _effort_meets(value: str, minimum: str) -> bool:
    return EFFORT_ORDER[value] >= EFFORT_ORDER[minimum] and value != "unknown"


def _unique_reason_codes(reason_codes: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for reason_code in reason_codes:
        if reason_code not in seen:
            unique.append(reason_code)
            seen.add(reason_code)
    return unique


def build_effort_aware_gardener_worthiness(
    *,
    promotion_request: Mapping[str, Any],
    actual_effort_estimate: str | None = None,
    minimum_required_effort: str = "high",
) -> dict[str, Any]:
    """Gate Gardener promotion review on verified effort metadata.

    This builder creates a reviewable worthiness decision. It never writes
    canonical vault state and it defers promotion review when effort status or
    actual effort evidence is unknown, downgraded, or below the required level.
    """

    validate_vault_promotion_request(promotion_request)
    minimum = _normalize_effort_level(minimum_required_effort)
    if minimum == "unknown":
        raise ValueError("minimum_required_effort must be a known effort level")

    effort_metadata = dict(promotion_request["effort_metadata"])
    effort_status = _normalize_effort_status(effort_metadata.get("effort_status"))
    requested_effort = _normalize_effort_level(effort_metadata.get("requested_effort"))
    applied_effort = _normalize_effort_level(effort_metadata.get("applied_effort"))
    actual_effort = _normalize_effort_level(
        actual_effort_estimate
        if actual_effort_estimate is not None
        else effort_metadata.get("actual_effort_estimate") or effort_metadata.get("actual_effort")
    )

    requested_known = requested_effort != "unknown"
    applied_known = applied_effort != "unknown"
    actual_known = actual_effort != "unknown"
    effort_status_accepted = effort_status == "verified"
    applied_effort_meets_minimum = _effort_meets(applied_effort, minimum)
    actual_effort_meets_minimum = _effort_meets(actual_effort, minimum)
    applied_effort_meets_requested = (
        requested_known and applied_known and EFFORT_ORDER[applied_effort] >= EFFORT_ORDER[requested_effort]
    )
    downgrade_detected = (
        effort_status == "downgraded"
        or (requested_known and applied_known and EFFORT_ORDER[applied_effort] < EFFORT_ORDER[requested_effort])
    )

    ready = (
        effort_status_accepted
        and requested_known
        and applied_known
        and actual_known
        and applied_effort_meets_minimum
        and actual_effort_meets_minimum
        and applied_effort_meets_requested
        and not downgrade_detected
    )

    reason_codes = [
        "effort_aware_gardener_worthiness_checked",
        "promotion_review_required",
        "canonical_write_not_authorized",
    ]
    if ready:
        reason_codes.extend(
            [
                "effort_status_verified",
                "applied_effort_meets_minimum",
                "actual_effort_meets_minimum",
            ]
        )
    else:
        reason_codes.append("effort_review_deferred")
        if not effort_status_accepted:
            reason_codes.append("effort_status_not_verified")
        if not requested_known:
            reason_codes.append("requested_effort_unknown")
        if not applied_known:
            reason_codes.append("applied_effort_unknown")
        if not actual_known:
            reason_codes.append("actual_effort_unknown")
        if applied_known and not applied_effort_meets_minimum:
            reason_codes.append("applied_effort_below_minimum")
        if actual_known and not actual_effort_meets_minimum:
            reason_codes.append("actual_effort_below_minimum")
        if downgrade_detected:
            reason_codes.append("effort_downgrade_detected")

    worthiness = {
        "schema_version": "effort_aware_gardener_worthiness.v1",
        "worthiness_id": uuid.uuid4().hex,
        "worthiness_status": "ready_for_promotion_review" if ready else "deferred_for_effort_review",
        "promotion_request_id": str(promotion_request["promotion_request_id"]),
        "candidate_id": str(promotion_request["candidate_id"]),
        "provider_id": str(promotion_request["provider_id"]),
        "provider_profile": str(promotion_request["provider_profile"]),
        "session_uid": str(promotion_request["session_uid"]),
        "requested_owner": str(promotion_request["requested_owner"]),
        "source_refs": [dict(ref) for ref in promotion_request["source_refs"]],
        "evaluator_verdict_ref": dict(promotion_request["evaluator_verdict_ref"]),
        "confidence": dict(promotion_request["confidence"]),
        "effort_assessment": {
            "effort_status": effort_status,
            "requested_effort": requested_effort,
            "applied_effort": applied_effort,
            "actual_effort_estimate": actual_effort,
            "minimum_required_effort": minimum,
            "effort_status_accepted": effort_status_accepted,
            "requested_effort_known": requested_known,
            "applied_effort_known": applied_known,
            "actual_effort_known": actual_known,
            "applied_effort_meets_minimum": applied_effort_meets_minimum,
            "actual_effort_meets_minimum": actual_effort_meets_minimum,
            "applied_effort_meets_requested": applied_effort_meets_requested,
            "downgrade_detected": downgrade_detected,
        },
        "gate_metadata": {
            "promotion_request_gate": "vault_promotion_request_required",
            "effort_status_gate": "verified_required",
            "actual_effort_gate": "minimum_required_before_review",
            "canonical_write_gate": "not_authorized_by_worthiness",
        },
        "promotion_review_required": True,
        "canonical_authority": "not_this_contract",
        "canonical_write_status": "not_written",
        "vault_mutation_allowed": False,
        "reason_codes": _unique_reason_codes(reason_codes),
        "created_at": utc_now_iso(),
    }
    validate_effort_aware_gardener_worthiness(worthiness)
    return worthiness
