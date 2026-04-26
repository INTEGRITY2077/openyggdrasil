from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso

from .vault_promotion_request import validate_vault_promotion_request
from .vault_record_lifecycle import validate_vault_record_lifecycle


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
CROSS_PROVIDER_CONFLICT_QUARANTINE_SCHEMA_PATH = (
    CONTRACTS_ROOT / "cross_provider_conflict_quarantine.v1.schema.json"
)
DISCOUNT_FACTOR = 0.5
CONFLICT_THRESHOLD = 0.5


@lru_cache(maxsize=1)
def load_cross_provider_conflict_quarantine_schema() -> dict[str, Any]:
    return json.loads(CROSS_PROVIDER_CONFLICT_QUARANTINE_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_cross_provider_conflict_quarantine(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_cross_provider_conflict_quarantine_schema(),
    )


def _has_safe_evidence_pointer(ref: Any) -> bool:
    if not isinstance(ref, Mapping):
        return False
    for key in ("path_hint", "path", "ref", "uri", "url"):
        if str(ref.get(key) or "").strip():
            return True
    canonical_ref = ref.get("canonical_ref")
    if isinstance(canonical_ref, Mapping):
        return _has_safe_evidence_pointer(canonical_ref)
    return False


def _has_provenanced_source_refs(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    source_refs = value.get("source_refs")
    return isinstance(source_refs, Sequence) and not isinstance(source_refs, (str, bytes)) and any(
        _has_safe_evidence_pointer(ref) for ref in source_refs
    ) and isinstance(value.get("provenance"), Mapping)


def _walk_raw_transcript_leaks(value: Any) -> int:
    leak_keys = {
        "raw_text",
        "raw_transcript",
        "raw_session",
        "session_dump",
        "transcript",
        "transcript_text",
        "conversation_excerpt",
        "provider_response_raw",
    }
    if isinstance(value, Mapping):
        count = 0
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in leak_keys:
                count += 1
            count += _walk_raw_transcript_leaks(child)
        return count
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sum(_walk_raw_transcript_leaks(child) for child in value)
    if isinstance(value, str):
        normalized = value.lower()
        if ("user:" in normalized and "assistant:" in normalized) or "raw transcript" in normalized:
            return 1
    return 0


def measure_cross_provider_provenance_metrics(
    quarantine: Mapping[str, Any],
    *,
    validate_contract: bool = True,
) -> dict[str, Any]:
    """Measure P9-S19 UX proof that cross-provider conflicts expose safe provenance only."""
    if validate_contract:
        validate_cross_provider_conflict_quarantine(quarantine)

    candidate_claim = quarantine.get("candidate_claim")
    candidate = dict(candidate_claim) if isinstance(candidate_claim, Mapping) else {}
    conflicting_records = [
        dict(record) for record in quarantine.get("conflicting_records") or [] if isinstance(record, Mapping)
    ]
    expected_groups = 1 + len(conflicting_records)

    covered_groups = int(_has_provenanced_source_refs(candidate))
    covered_groups += sum(int(_has_provenanced_source_refs(record)) for record in conflicting_records)
    provenance_coverage = round(covered_groups / expected_groups, 6) if expected_groups else 1.0

    safe_pointer_groups = int(
        isinstance(candidate.get("source_refs"), Sequence)
        and not isinstance(candidate.get("source_refs"), (str, bytes))
        and any(_has_safe_evidence_pointer(ref) for ref in candidate.get("source_refs", []))
    )
    for record in conflicting_records:
        source_refs = record.get("source_refs")
        if isinstance(source_refs, Sequence) and not isinstance(source_refs, (str, bytes)):
            safe_pointer_groups += int(any(_has_safe_evidence_pointer(ref) for ref in source_refs))
    safe_evidence_pointer_coverage = round(safe_pointer_groups / expected_groups, 6) if expected_groups else 1.0

    reason_codes = {
        str(code)
        for code in quarantine.get("reason_codes") or []
        if isinstance(code, str) and code.strip()
    }
    review_route = quarantine.get("review_route") if isinstance(quarantine.get("review_route"), Mapping) else {}
    conflict_boundary_visible = (
        bool(conflicting_records)
        and review_route.get("fallback_action") == "quarantine_until_review"
        and quarantine.get("canonical_write_status") == "not_written"
        and quarantine.get("vault_mutation_allowed") is False
        and quarantine.get("ambiguous_memory_canonicalized") is False
        and "cross_provider_conflict_detected" in reason_codes
    )
    silent_conflict_count = 0 if conflict_boundary_visible else max(1, len(conflicting_records))
    raw_transcript_leak_count = _walk_raw_transcript_leaks(quarantine)

    failing_metrics: list[str] = []
    if provenance_coverage < 1.0:
        failing_metrics.append("provenance_coverage")
    if safe_evidence_pointer_coverage < 1.0:
        failing_metrics.append("safe_evidence_pointer_coverage")
    if silent_conflict_count:
        failing_metrics.append("silent_conflict_count")
    if raw_transcript_leak_count:
        failing_metrics.append("raw_transcript_leak_count")

    return {
        "scenario_id": "P9-S19",
        "surface_id": "UX-FS-05",
        "secondary_surface_id": "UX-FS-06",
        "provenance_coverage": provenance_coverage,
        "safe_evidence_pointer_coverage": safe_evidence_pointer_coverage,
        "silent_conflict_count": silent_conflict_count,
        "raw_transcript_leak_count": raw_transcript_leak_count,
        "conflict_record_count": len(conflicting_records),
        "failing_metrics": failing_metrics,
        "decision": "green_passed" if not failing_metrics else "red_captured",
    }


def _normalize_claim_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not text:
        raise ValueError("claim_text is required")
    return text


def _require_mapping(name: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not dict(value):
        raise ValueError(f"{name} is required")
    return dict(value)


def _source_refs(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs = [dict(ref) for ref in values if isinstance(ref, Mapping) and dict(ref)]
    if not refs:
        raise ValueError("source_refs are required")
    return refs


def _candidate_claim(candidate_claim: Mapping[str, Any], promotion_request: Mapping[str, Any]) -> dict[str, Any]:
    claim_key = str(candidate_claim.get("claim_key") or "").strip()
    claim_text = str(candidate_claim.get("claim_text") or "").strip()
    if not claim_key:
        raise ValueError("candidate claim_key is required")
    normalized_claim = str(candidate_claim.get("normalized_claim") or _normalize_claim_text(claim_text)).strip()
    confidence_score = float(
        candidate_claim.get(
            "confidence_score",
            promotion_request.get("confidence", {}).get("confidence_score", 0.0),
        )
    )
    return {
        "claim_key": claim_key,
        "claim_text": claim_text,
        "normalized_claim": normalized_claim,
        "confidence_score": confidence_score,
        "source_refs": _source_refs(candidate_claim.get("source_refs") or promotion_request.get("source_refs") or []),
        "provenance": _require_mapping(
            "candidate provenance",
            candidate_claim.get("provenance") or promotion_request.get("provenance"),
        ),
    }


def _record_provider(record: Mapping[str, Any]) -> tuple[str, str | None]:
    provenance = _require_mapping("record provenance", record.get("provenance"))
    provider_id = str(provenance.get("provider_id") or "").strip()
    if not provider_id:
        raise ValueError("active record provenance.provider_id is required for cross-provider conflict checks")
    provider_profile = provenance.get("provider_profile")
    return provider_id, str(provider_profile).strip() if provider_profile is not None else None


def detect_cross_provider_conflicts(
    *,
    promotion_request: Mapping[str, Any],
    candidate_claim: Mapping[str, Any],
    active_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    validate_vault_promotion_request(promotion_request)
    candidate = _candidate_claim(candidate_claim, promotion_request)
    candidate_provider = str(promotion_request["provider_id"])
    conflicts: list[dict[str, Any]] = []
    for record in active_records:
        validate_vault_record_lifecycle(record)
        if record.get("lifecycle_state") != "ACTIVE":
            continue
        record_provider, record_profile = _record_provider(record)
        if record_provider == candidate_provider:
            continue
        provenance = dict(record["provenance"])
        record_claim_key = str(provenance.get("claim_key") or "").strip()
        if record_claim_key != candidate["claim_key"]:
            continue
        record_normalized_claim = provenance.get("normalized_claim")
        if record_normalized_claim:
            record_normalized_claim = _normalize_claim_text(record_normalized_claim)
            conflict_kind = (
                "cross_provider_contradiction"
                if record_normalized_claim != candidate["normalized_claim"]
                else None
            )
            conflict_score = 1.0 if conflict_kind else 0.0
        else:
            conflict_kind = "cross_provider_ambiguous_claim"
            conflict_score = CONFLICT_THRESHOLD
        if not conflict_kind or conflict_score < CONFLICT_THRESHOLD:
            continue
        conflicts.append(
            {
                "lifecycle_record_id": str(record["lifecycle_record_id"]),
                "canonical_record_id": str(record["canonical_record_id"]),
                "lifecycle_state": "ACTIVE",
                "provider_id": record_provider,
                "provider_profile": record_profile,
                "claim_key": record_claim_key,
                "normalized_claim": record_normalized_claim,
                "conflict_kind": conflict_kind,
                "conflict_score": conflict_score,
                "source_refs": [dict(ref) for ref in record["source_refs"]],
                "provenance": provenance,
                "canonical_ref": dict(record["canonical_ref"]),
                "archive_trace_refs": [dict(ref) for ref in record["archive_trace_refs"]],
            }
        )
    return conflicts


def build_cross_provider_conflict_quarantine(
    *,
    promotion_request: Mapping[str, Any],
    candidate_claim: Mapping[str, Any],
    active_records: Sequence[Mapping[str, Any]],
    review_owner: str = "vault_conflict_review",
) -> dict[str, Any]:
    validate_vault_promotion_request(promotion_request)
    candidate = _candidate_claim(candidate_claim, promotion_request)
    conflicts = detect_cross_provider_conflicts(
        promotion_request=promotion_request,
        candidate_claim=candidate,
        active_records=active_records,
    )
    if not conflicts:
        raise ValueError("cross-provider conflict evidence is required for quarantine")

    original_confidence = float(candidate["confidence_score"])
    discounted_confidence = round(original_confidence * DISCOUNT_FACTOR, 6)
    quarantine = {
        "schema_version": "cross_provider_conflict_quarantine.v1",
        "quarantine_id": uuid.uuid4().hex,
        "quarantine_status": "quarantined_for_review",
        "candidate_promotion_request_id": str(promotion_request["promotion_request_id"]),
        "candidate_provider_id": str(promotion_request["provider_id"]),
        "candidate_provider_profile": str(promotion_request["provider_profile"]),
        "candidate_session_uid": str(promotion_request["session_uid"]),
        "candidate_claim": candidate,
        "conflicting_records": conflicts,
        "cross_provider_discounting": {
            "rule_id": "cross_provider_conflict_discount_v1",
            "rule_summary": (
                "Cross-provider claims with matching claim_key and contradictory or ambiguous "
                "content are discounted and quarantined until review."
            ),
            "discount_applied": True,
            "original_confidence": original_confidence,
            "discount_factor": DISCOUNT_FACTOR,
            "discounted_confidence": discounted_confidence,
            "conflict_threshold": CONFLICT_THRESHOLD,
            "requires_quarantine": True,
        },
        "review_route": {
            "review_status": "pending_conflict_review",
            "review_owner": review_owner,
            "fallback_action": "quarantine_until_review",
        },
        "canonical_authority": "not_this_contract",
        "canonical_write_status": "not_written",
        "vault_mutation_allowed": False,
        "ambiguous_memory_canonicalized": False,
        "reason_codes": [
            "cross_provider_conflict_detected",
            "cross_provider_discount_applied",
            "quarantined_for_review",
            "canonical_write_not_authorized",
            "ambiguous_memory_not_canonicalized",
        ],
        "created_at": utc_now_iso(),
    }
    validate_cross_provider_conflict_quarantine(quarantine)
    return quarantine
