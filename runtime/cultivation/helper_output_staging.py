from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso
from reasoning.reasoning_lease_contracts import validate_reasoning_lease_result

from .effort_aware_gardener_worthiness import validate_effort_aware_gardener_worthiness


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
HELPER_OUTPUT_STAGING_SCHEMA_PATH = CONTRACTS_ROOT / "helper_output_staging.v1.schema.json"

SAFE_OUTPUT_FLAGS = (
    "raw_transcript_copied",
    "raw_session_copied",
    "state_db_result_harvested",
    "foreground_context_appended",
)


@lru_cache(maxsize=1)
def load_helper_output_staging_schema() -> dict[str, Any]:
    return json.loads(HELPER_OUTPUT_STAGING_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_helper_output_staging(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_helper_output_staging_schema())


def _require_text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _require_source_refs(value: Any) -> list[str]:
    refs = [str(ref).strip() for ref in (value or []) if str(ref).strip()]
    if not refs:
        raise ValueError("helper output source_refs are required before staging")
    return refs[:32]


def _ensure_no_raw_helper_material(output: Mapping[str, Any]) -> None:
    for flag_name in SAFE_OUTPUT_FLAGS:
        if output.get(flag_name) is True:
            raise ValueError(f"{flag_name} must be false before helper output staging")


def build_helper_output_staging(
    *,
    lease_result: Mapping[str, Any],
    worthiness: Mapping[str, Any],
) -> dict[str, Any]:
    """Stage a completed helper/lease result for later promotion review.

    Staging accepts only completed lease results with digest/source-ref evidence
    and a ready effort-aware Gardener worthiness decision. It never promotes or
    writes the helper output as canonical vault memory.
    """

    validate_reasoning_lease_result(lease_result)
    validate_effort_aware_gardener_worthiness(worthiness)

    if lease_result.get("lease_status") != "completed":
        raise ValueError("completed lease result is required before helper output staging")
    if worthiness.get("worthiness_status") != "ready_for_promotion_review":
        raise ValueError("ready effort-aware Gardener worthiness is required before helper output staging")

    output = dict(lease_result.get("output") or {})
    _ensure_no_raw_helper_material(output)

    provider_id = _require_text("lease_result.provider_id", lease_result.get("provider_id"))
    if provider_id != str(worthiness.get("provider_id")):
        raise ValueError("helper output provider must match the effort-aware worthiness provider")

    provider_profile = _require_text("lease_result.provider_profile", lease_result.get("provider_profile"))
    provider_session_id = _require_text(
        "lease_result.provider_session_id",
        lease_result.get("provider_session_id"),
    )
    worker_ref = _require_text("lease_result.worker_ref", lease_result.get("worker_ref") or output.get("worker_ref"))
    result_source_ref = _require_text("output.result_source_ref", output.get("result_source_ref"))
    result_digest = _require_text("output.result_digest_sha256", output.get("result_digest_sha256"))
    effort_status = _require_text("output.effort_status", output.get("effort_status"))
    if effort_status not in {"verified", "accepted"}:
        raise ValueError("verified or accepted helper effort is required before staging")
    actual_effort_estimate = _require_text(
        "output.actual_effort_estimate",
        output.get("actual_effort_estimate"),
    )
    source_refs = _require_source_refs(output.get("source_refs"))

    staging = {
        "schema_version": "helper_output_staging.v1",
        "staging_id": uuid.uuid4().hex,
        "staging_status": "staged_for_promotion_review",
        "promotion_request_id": str(worthiness["promotion_request_id"]),
        "candidate_id": str(worthiness["candidate_id"]),
        "worthiness_id": str(worthiness["worthiness_id"]),
        "lease_result_ref": {
            "lease_result_id": str(lease_result["lease_result_id"]),
            "lease_request_id": str(lease_result["lease_request_id"]),
            "lease_status": "completed",
            "producer_role": str(lease_result["producer_role"]),
            "provider_id": provider_id,
            "provider_profile": provider_profile,
            "provider_session_id": provider_session_id,
            "worker_ref": worker_ref,
            "confidence_score": float(lease_result["confidence_score"]),
            "completed_at": str(lease_result["completed_at"]),
        },
        "staged_output_ref": {
            "result_source_ref": result_source_ref,
            "result_digest_sha256": result_digest,
            "result_preview": output.get("result_preview"),
            "preview_max_chars": int(output.get("preview_max_chars") or 512),
            "source_refs": source_refs,
            "effort_status": effort_status,
            "actual_effort_estimate": actual_effort_estimate,
            "raw_transcript_copied": False,
            "raw_session_copied": False,
            "state_db_result_harvested": False,
            "foreground_context_appended": False,
        },
        "validation_metadata": {
            "lease_gate": "completed_lease_required",
            "worthiness_gate": "ready_effort_aware_worthiness_required",
            "source_ref_gate": "digest_preview_source_ref_required",
            "raw_surface_gate": "no_raw_provider_material",
            "canonical_write_gate": "not_authorized_by_staging",
        },
        "promotion_review_required": True,
        "staging_authority": "staging_only",
        "canonical_authority": "not_this_contract",
        "canonical_write_status": "not_written",
        "vault_mutation_allowed": False,
        "helper_output_canonicalized": False,
        "reason_codes": [
            "helper_output_staged_for_review",
            "completed_lease_required",
            "effort_aware_worthiness_ready",
            "digest_source_ref_required",
            "raw_provider_material_not_stored",
            "canonical_write_not_authorized",
        ],
        "created_at": utc_now_iso(),
    }
    validate_helper_output_staging(staging)
    return staging
