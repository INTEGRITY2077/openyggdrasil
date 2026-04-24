from __future__ import annotations

import uuid
from typing import Any, Mapping

from harness_common import utc_now_iso
from reasoning.reasoning_lease_contracts import (
    provider_supports_background_reasoning,
    validate_reasoning_lease_request,
    validate_reasoning_lease_result,
)


def _session_uid(provider_descriptor: Mapping[str, Any]) -> str | None:
    value = provider_descriptor.get("session_uid")
    return str(value) if value else None


def build_provider_headless_lease_request(
    *,
    provider_descriptor: Mapping[str, Any],
    requested_by_role: str,
    job_type: str,
    objective: str,
    input_refs: Mapping[str, Any],
    priority: str = "medium",
    fallback_policy: str = "deterministic_base_path",
    expected_output_schema: str | None = None,
) -> dict[str, Any]:
    request = {
        "schema_version": "reasoning_lease_request.v1",
        "lease_request_id": uuid.uuid4().hex,
        "requested_by_role": requested_by_role,
        "provider_id": provider_descriptor.get("provider_id"),
        "provider_profile": provider_descriptor.get("provider_profile"),
        "provider_session_id": provider_descriptor.get("provider_session_id"),
        "session_uid": _session_uid(provider_descriptor),
        "capability": "background_reasoning",
        "job_type": job_type,
        "priority": priority,
        "inference_mode": "provider_headless",
        "objective": objective,
        "input_refs": dict(input_refs),
        "constraints": [
            "do_not_request_api_key",
            "do_not_request_oauth",
            "do_not_copy_raw_provider_session",
            "use_source_refs_only",
        ],
        "expected_output_schema": expected_output_schema,
        "fallback_policy": fallback_policy,
        "requested_at": utc_now_iso(),
        "expires_at": None,
    }
    validate_reasoning_lease_request(request)
    return request


def decline_provider_headless_lease(
    request: Mapping[str, Any],
    *,
    reason_code: str,
    producer_role: str = "provider_resource_boundary",
) -> dict[str, Any]:
    validate_reasoning_lease_request(request)
    result = {
        "schema_version": "reasoning_lease_result.v1",
        "lease_result_id": uuid.uuid4().hex,
        "lease_request_id": request["lease_request_id"],
        "lease_status": "declined",
        "producer_role": producer_role,
        "provider_id": request.get("provider_id"),
        "provider_profile": request.get("provider_profile"),
        "provider_session_id": request.get("provider_session_id"),
        "worker_ref": None,
        "fallback_used": False,
        "output": {
            "decision": "declined",
            "reason_code": reason_code,
            "fallback_policy": request.get("fallback_policy"),
        },
        "confidence_score": 1.0,
        "failure_reason": reason_code,
        "completed_at": utc_now_iso(),
    }
    validate_reasoning_lease_result(result)
    return result


def fallback_reasoning_lease_result(
    request: Mapping[str, Any],
    *,
    reason_code: str,
    output: Mapping[str, Any] | None = None,
    producer_role: str = "provider_resource_boundary",
) -> dict[str, Any]:
    validate_reasoning_lease_request(request)
    payload = {
        "decision": "fallback",
        "reason_code": reason_code,
        "fallback_policy": request.get("fallback_policy"),
        "fallback_output": dict(output or {}),
    }
    result = {
        "schema_version": "reasoning_lease_result.v1",
        "lease_result_id": uuid.uuid4().hex,
        "lease_request_id": request["lease_request_id"],
        "lease_status": "fallback_used",
        "producer_role": producer_role,
        "provider_id": request.get("provider_id"),
        "provider_profile": request.get("provider_profile"),
        "provider_session_id": request.get("provider_session_id"),
        "worker_ref": None,
        "fallback_used": True,
        "output": payload,
        "confidence_score": 1.0,
        "failure_reason": None,
        "completed_at": utc_now_iso(),
    }
    validate_reasoning_lease_result(result)
    return result


def resolve_provider_resource_request(
    *,
    provider_descriptor: Mapping[str, Any],
    request: Mapping[str, Any],
    provider_declined: bool = False,
    fallback_output: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_reasoning_lease_request(request)
    if request.get("inference_mode") != "provider_headless":
        return fallback_reasoning_lease_result(
            request,
            reason_code="non_provider_headless_request",
            output=fallback_output,
        )
    if not provider_supports_background_reasoning(provider_descriptor):
        return fallback_reasoning_lease_result(
            request,
            reason_code="provider_background_reasoning_unavailable",
            output=fallback_output,
        )
    if provider_declined:
        return decline_provider_headless_lease(
            request,
            reason_code="provider_declined_headless_worker",
        )
    return decline_provider_headless_lease(
        request,
        reason_code="provider_headless_handoff_not_implemented",
    )
