from __future__ import annotations

import hashlib
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso
from reasoning.hermes_background_task_capture import validate_hermes_background_task_capture
from reasoning.reasoning_lease_contracts import (
    validate_reasoning_lease_request,
    validate_reasoning_lease_result,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

HERMES_BACKGROUND_TASK_CAPTURE_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_phase-4-hermes-background-task-capture.md"
)

P4_H3_ACTION = "P4.H3.hermes-background-result-contract"
P4_H4_ACTION = "P4.H4.hermes-background-unavailable-contract"

RESULT_GATE_STATUSES = {"allowed", "blocked", "unavailable"}
NON_COMPLETABLE_EFFORT_STATUSES = {
    "downgraded",
    "below_minimum",
    "unknown",
    "unavailable",
    "unverified",
}

DEFAULT_TOKEN_USAGE = {
    "input_tokens": None,
    "output_tokens": None,
    "total_tokens": None,
}

DEFAULT_SAFETY_FLAGS = {
    "raw_transcript_copied": False,
    "raw_session_copied": False,
    "state_db_result_harvested": False,
    "foreground_context_appended": False,
}

UNSAFE_REASON_CODES = {
    "raw_transcript_copied": "raw_provider_transcript_copy_not_allowed",
    "raw_session_copied": "raw_provider_session_copy_not_allowed",
    "state_db_result_harvested": "state_db_result_harvesting_not_allowed",
    "foreground_context_appended": "foreground_context_append_not_allowed",
}


@lru_cache(maxsize=1)
def load_hermes_background_result_contract_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_background_result_contract.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_background_result_contract(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_background_result_contract_schema(),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_preview(value: str | None, *, preview_max_chars: int) -> str | None:
    if value is None:
        return None
    return value[:preview_max_chars]


def _first_unsafe_reason(safety: Mapping[str, bool]) -> str | None:
    for flag_name, reason_code in UNSAFE_REASON_CODES.items():
        if safety.get(flag_name) is True:
            return reason_code
    return None


def _normalized_token_usage(token_usage: Mapping[str, Any] | None) -> dict[str, int | None]:
    values = dict(DEFAULT_TOKEN_USAGE)
    values.update(dict(token_usage or {}))
    return {
        "input_tokens": values.get("input_tokens"),
        "output_tokens": values.get("output_tokens"),
        "total_tokens": values.get("total_tokens"),
    }


def _clamped_confidence(value: float | int | None, *, completed: bool) -> float:
    if value is None:
        return 0.0 if not completed else 0.5
    return max(0.0, min(1.0, float(value)))


def _resolve_gate(
    *,
    requested_gate_status: str | None,
    requested_reason_code: str | None,
    task_capture: Mapping[str, Any],
    result_source_ref: str | None,
    worker_ref: str | None,
    effort_status: str,
    unsafe_reason_code: str | None,
) -> tuple[str, str | None]:
    if unsafe_reason_code is not None:
        return "blocked", unsafe_reason_code

    if task_capture.get("capture_status") != "captured" or not task_capture.get("captured_task_ref"):
        return "unavailable", "background_task_ref_unavailable"

    if requested_gate_status not in RESULT_GATE_STATUSES:
        return "unavailable", "result_gate_status_missing_or_invalid"

    if requested_gate_status == "blocked":
        return "blocked", requested_reason_code or "result_gate_blocked"

    if requested_gate_status == "unavailable":
        return "unavailable", requested_reason_code or "result_gate_unavailable"

    if not result_source_ref or not worker_ref:
        return "unavailable", "allowed_result_missing_source_ref_or_worker_ref"

    if effort_status in NON_COMPLETABLE_EFFORT_STATUSES:
        return "unavailable", "effort_not_verifiable_for_completed_lease"

    return "allowed", requested_reason_code


def _lease_status_for_gate(result_gate_status: str) -> str:
    if result_gate_status == "allowed":
        return "completed"
    if result_gate_status == "blocked":
        return "failed"
    return "unavailable"


def build_hermes_background_reasoning_lease_result(
    *,
    lease_request: Mapping[str, Any],
    task_capture: Mapping[str, Any],
    result_gate_status: str | None,
    result_text: str | None = None,
    result_source_ref: str | None = None,
    worker_ref: str | None = None,
    result_gate_reason_code: str | None = None,
    confidence_score: float | int | None = None,
    token_usage: Mapping[str, Any] | None = None,
    duration_ms: int | None = None,
    tool_call_count: int | None = None,
    requested_effort: str | None = None,
    applied_effort: str | None = None,
    normalized_effort: str | None = None,
    effort_status: str | None = None,
    actual_effort_estimate: str | None = None,
    evidence_refs: Sequence[str] = (HERMES_BACKGROUND_TASK_CAPTURE_REF,),
    safety_flags: Mapping[str, bool] | None = None,
    preview_max_chars: int = 512,
    producer_role: str = "hermes_background_result_contract",
) -> dict[str, Any]:
    """Convert a Hermes background task result into a gated lease result.

    A completed lease is emitted only when the task reference exists, the result
    gate is allowed, source/worker refs are present, and effort metadata is
    verified or explicitly accepted. Provider transcripts and sessions are
    never copied into the result envelope.
    """

    validate_reasoning_lease_request(lease_request)
    validate_hermes_background_task_capture(task_capture)

    bounded_preview_chars = max(1, min(512, int(preview_max_chars)))
    normalized_effort_status = effort_status or "unknown"

    safety = dict(DEFAULT_SAFETY_FLAGS)
    safety.update(dict(safety_flags or {}))
    unsafe_reason_code = _first_unsafe_reason(safety)

    gate_status, gate_reason_code = _resolve_gate(
        requested_gate_status=result_gate_status,
        requested_reason_code=result_gate_reason_code,
        task_capture=task_capture,
        result_source_ref=result_source_ref,
        worker_ref=worker_ref,
        effort_status=normalized_effort_status,
        unsafe_reason_code=unsafe_reason_code,
    )
    lease_status = _lease_status_for_gate(gate_status)
    completed = lease_status == "completed"

    source_refs = [str(ref) for ref in evidence_refs]
    source_refs.extend(str(ref) for ref in task_capture.get("source_refs") or [])
    if result_source_ref:
        source_refs.append(str(result_source_ref))

    output = {
        "schema_version": "hermes_background_result_contract.v1",
        "result_contract_id": uuid.uuid4().hex,
        "provider_id": str(task_capture.get("provider_id")),
        "provider_profile": str(task_capture.get("provider_profile")),
        "provider_session_id": str(task_capture.get("provider_session_id")),
        "capture_id": str(task_capture.get("capture_id")),
        "captured_task_ref": task_capture.get("captured_task_ref"),
        "result_gate_status": gate_status,
        "result_gate_reason_code": gate_reason_code,
        "lease_status_decision": lease_status,
        "result_source_ref": result_source_ref,
        "worker_ref": worker_ref,
        "result_preview": _bounded_preview(result_text, preview_max_chars=bounded_preview_chars),
        "preview_max_chars": bounded_preview_chars,
        "result_digest_sha256": _sha256_text(result_text) if result_text is not None else None,
        "confidence_score": _clamped_confidence(confidence_score, completed=completed),
        "token_usage": _normalized_token_usage(token_usage),
        "duration_ms": duration_ms,
        "tool_call_count": tool_call_count,
        "requested_effort": requested_effort,
        "applied_effort": applied_effort,
        "normalized_effort": normalized_effort,
        "effort_status": normalized_effort_status,
        "actual_effort_estimate": actual_effort_estimate,
        "raw_transcript_copied": False,
        "raw_session_copied": False,
        "state_db_result_harvested": False,
        "foreground_context_appended": False,
        "source_refs": source_refs[:32],
        "next_action": P4_H4_ACTION if completed else P4_H3_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_background_result_contract(output)

    result = {
        "schema_version": "reasoning_lease_result.v1",
        "lease_result_id": uuid.uuid4().hex,
        "lease_request_id": lease_request["lease_request_id"],
        "lease_status": lease_status,
        "producer_role": producer_role,
        "provider_id": lease_request.get("provider_id"),
        "provider_profile": lease_request.get("provider_profile"),
        "provider_session_id": lease_request.get("provider_session_id"),
        "worker_ref": worker_ref if completed else worker_ref,
        "fallback_used": lease_status == "fallback_used",
        "output": output,
        "confidence_score": output["confidence_score"],
        "failure_reason": None if completed else gate_reason_code,
        "completed_at": utc_now_iso(),
    }
    validate_reasoning_lease_result(result)
    return result
