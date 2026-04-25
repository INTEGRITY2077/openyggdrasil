from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
PROVIDER_EFFORT_VOCABULARY_NORMALIZATION_SCHEMA_PATH = (
    CONTRACTS_ROOT / "provider_effort_vocabulary_normalization.v1.schema.json"
)
P6_S2_ACTION = "P6.S2.packaging-known-limitations-matrix"

EFFORT_LEVEL_VALUES = {"unknown", "low", "medium", "high", "xhigh"}
LOW_EFFORT_TOKENS = {"low", "minimal", "small", "light", "cheap"}
MEDIUM_EFFORT_TOKENS = {"medium", "med", "normal", "standard", "balanced", "default"}
HIGH_EFFORT_TOKENS = {"high", "large", "deep", "hard", "provider_reported_high"}
XHIGH_EFFORT_TOKENS = {
    "xhigh",
    "x_high",
    "extra_high",
    "extrahigh",
    "very_high",
    "max",
    "maximum",
    "provider_reported_xhigh",
}
UNAVAILABLE_STATUS_TOKENS = {"unavailable", "unsupported", "declined", "timeout", "cancelled", "canceled"}
DECLARED_STATUS_TOKENS = {"declared", "reported", "provider_reported", "accepted"}


@lru_cache(maxsize=1)
def load_provider_effort_vocabulary_normalization_schema() -> dict[str, Any]:
    return json.loads(
        PROVIDER_EFFORT_VOCABULARY_NORMALIZATION_SCHEMA_PATH.read_text(encoding="utf-8")
    )


def validate_provider_effort_vocabulary_normalization(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_provider_effort_vocabulary_normalization_schema(),
    )


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_effort_level(value: Any) -> str:
    token = _token(value)
    if token in EFFORT_LEVEL_VALUES:
        return token
    if token in LOW_EFFORT_TOKENS:
        return "low"
    if token in MEDIUM_EFFORT_TOKENS:
        return "medium"
    if token in HIGH_EFFORT_TOKENS:
        return "high"
    if token in XHIGH_EFFORT_TOKENS:
        return "xhigh"
    if token.startswith("provider_reported_"):
        return normalize_effort_level(token.removeprefix("provider_reported_"))
    return "unknown"


def normalize_gardener_effort_status(value: Any) -> str:
    token = _token(value)
    if token == "verified":
        return "verified"
    if token == "downgraded":
        return "downgraded"
    if token in UNAVAILABLE_STATUS_TOKENS:
        return "unavailable"
    if token in DECLARED_STATUS_TOKENS:
        return "declared"
    return "unknown"


def normalize_helper_staging_effort_status(value: Any) -> str:
    token = _token(value)
    if token == "verified":
        return "verified"
    if token == "accepted":
        return "accepted"
    if token in UNAVAILABLE_STATUS_TOKENS or token == "downgraded":
        return "not_stageable"
    return "unknown"


def _status_bridge(*, gardener_status: str, helper_status: str) -> str:
    if gardener_status == "verified" and helper_status == "verified":
        return "gardener_verified_and_helper_verified"
    if gardener_status == "declared" and helper_status == "accepted":
        return "helper_accepted_not_gardener_verified"
    if gardener_status == "declared":
        return "declared_not_verified"
    if gardener_status in {"downgraded", "unavailable"} or helper_status == "not_stageable":
        return "downgraded_or_unavailable"
    return "unknown"


def _unique_reason_codes(reason_codes: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for reason_code in reason_codes:
        if reason_code not in seen:
            unique.append(reason_code)
            seen.add(reason_code)
    return unique


def _raw_string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_provider_effort_vocabulary_normalization(
    *,
    provider_id: str,
    provider_family: str,
    provider_profile: str,
    provider_session_id: str,
    raw_effort_metadata: Mapping[str, Any],
    source_kind: str = "provider_packaging",
    next_action: str = P6_S2_ACTION,
) -> dict[str, Any]:
    requested_effort_raw = raw_effort_metadata.get("requested_effort")
    applied_effort_raw = raw_effort_metadata.get("applied_effort")
    actual_effort_raw = raw_effort_metadata.get("actual_effort_estimate")
    effort_status_raw = raw_effort_metadata.get("effort_status")

    requested_effort = normalize_effort_level(requested_effort_raw)
    applied_effort = normalize_effort_level(applied_effort_raw)
    actual_effort = normalize_effort_level(actual_effort_raw)
    gardener_status = normalize_gardener_effort_status(effort_status_raw)
    helper_status = normalize_helper_staging_effort_status(effort_status_raw)
    status_bridge = _status_bridge(gardener_status=gardener_status, helper_status=helper_status)

    known_levels = {requested_effort, applied_effort, actual_effort} - {"unknown"}
    lossy_normalization = (
        len(known_levels) < 3
        or any(
            _raw_string_or_none(raw_value) is not None
            and normalized != _token(raw_value)
            and normalized != "unknown"
            for raw_value, normalized in (
                (requested_effort_raw, requested_effort),
                (applied_effort_raw, applied_effort),
                (actual_effort_raw, actual_effort),
            )
        )
    )

    reason_codes = [
        "provider_effort_vocabulary_normalized",
        "raw_provider_effort_preserved",
        "cross_provider_comparison_uses_normalized_fields",
        "canonical_write_not_authorized",
    ]
    if gardener_status != "verified":
        reason_codes.append("gardener_effort_not_verified")
    if helper_status == "accepted":
        reason_codes.append("helper_accepted_not_gardener_verified")
    if "unknown" in {requested_effort, applied_effort, actual_effort}:
        reason_codes.append("unknown_effort_level_present")
    if lossy_normalization:
        reason_codes.append("lossy_effort_normalization_visible")

    payload = {
        "schema_version": "provider_effort_vocabulary_normalization.v1",
        "normalization_id": uuid.uuid4().hex,
        "provider_ref": {
            "provider_id": str(provider_id),
            "provider_family": str(provider_family),
            "provider_profile": str(provider_profile),
            "provider_session_id": str(provider_session_id),
        },
        "raw_effort_metadata": {
            "source_kind": source_kind if source_kind in {
                "provider_packaging",
                "promotion_request",
                "reasoning_lease_result",
                "helper_output",
                "unknown",
            } else "unknown",
            "effort_status": _raw_string_or_none(effort_status_raw),
            "requested_effort": _raw_string_or_none(requested_effort_raw),
            "applied_effort": _raw_string_or_none(applied_effort_raw),
            "actual_effort_estimate": _raw_string_or_none(actual_effort_raw),
            "provider_specific": dict(raw_effort_metadata.get("provider_specific") or {}),
        },
        "normalized_effort": {
            "requested_effort": requested_effort,
            "applied_effort": applied_effort,
            "actual_effort_estimate": actual_effort,
            "gardener_effort_status": gardener_status,
            "helper_staging_effort_status": helper_status,
            "promotion_review_eligible": gardener_status == "verified"
            and "unknown" not in {requested_effort, applied_effort, actual_effort},
            "helper_staging_eligible": helper_status in {"verified", "accepted"}
            and actual_effort != "unknown",
            "lossy_normalization": lossy_normalization,
            "raw_values_preserved": True,
        },
        "cross_provider_usage": {
            "comparison_level_fields": [
                "requested_effort",
                "applied_effort",
                "actual_effort_estimate",
            ],
            "status_bridge": status_bridge,
            "raw_values_for_cross_provider_comparison": False,
            "canonical_write_status": "not_written",
            "vault_mutation_allowed": False,
        },
        "safety": {
            "provider_specific_contract_bypass": False,
            "raw_provider_effort_discarded": False,
            "helper_accepted_promoted_to_gardener_verified": False,
            "global_effort_equivalence_claimed": False,
            "phase5_memory_gates_weakened": False,
        },
        "reason_codes": _unique_reason_codes(reason_codes),
        "next_action": next_action,
        "created_at": utc_now_iso(),
    }
    validate_provider_effort_vocabulary_normalization(payload)
    return payload
