from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso
from reasoning.reasoning_lease_contracts import (
    validate_reasoning_lease_request,
    validate_reasoning_lease_result,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

HERMES_BACKGROUND_RESULT_CONTRACT_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_phase-4-hermes-background-result-contract.md"
)

P4_H5_ACTION = "P4.H5.hermes-state-metadata-only-policy"

UNAVAILABLE_KIND_DEFINITIONS: dict[str, dict[str, str]] = {
    "unsupported_provider": {
        "reason_code": "provider_background_reasoning_unsupported",
        "lease_status": "unavailable",
        "runner_outcome": "provider_unavailable",
        "fault_domain": "provider",
    },
    "provider_declined": {
        "reason_code": "provider_declined_background_reasoning",
        "lease_status": "declined",
        "runner_outcome": "provider_declined",
        "fault_domain": "provider",
    },
    "provider_timeout": {
        "reason_code": "provider_background_task_timeout",
        "lease_status": "unavailable",
        "runner_outcome": "provider_timeout",
        "fault_domain": "provider",
    },
    "provider_cancelled": {
        "reason_code": "provider_background_task_cancelled",
        "lease_status": "unavailable",
        "runner_outcome": "provider_cancelled",
        "fault_domain": "provider",
    },
    "no_visible_result": {
        "reason_code": "provider_background_result_not_visible",
        "lease_status": "unavailable",
        "runner_outcome": "result_unavailable",
        "fault_domain": "provider_result",
    },
    "handoff_gate_blocked": {
        "reason_code": "handoff_gate_blocked_result",
        "lease_status": "failed",
        "runner_outcome": "handoff_blocked",
        "fault_domain": "handoff_gate",
    },
    "handoff_gate_unavailable": {
        "reason_code": "handoff_gate_unavailable",
        "lease_status": "unavailable",
        "runner_outcome": "handoff_unavailable",
        "fault_domain": "handoff_gate",
    },
    "effort_below_minimum": {
        "reason_code": "effort_below_minimum",
        "lease_status": "unavailable",
        "runner_outcome": "effort_below_minimum",
        "fault_domain": "effort_policy",
    },
    "effort_unknown_unverifiable": {
        "reason_code": "effort_unknown_or_unverifiable",
        "lease_status": "unavailable",
        "runner_outcome": "effort_unverifiable",
        "fault_domain": "effort_policy",
    },
    "sandbox_security_unavailable": {
        "reason_code": "lease_security_sandbox_unavailable",
        "lease_status": "unavailable",
        "runner_outcome": "lease_security_unavailable",
        "fault_domain": "lease_security",
    },
}


@lru_cache(maxsize=1)
def load_hermes_background_unavailable_contract_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_background_unavailable_contract.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_background_unavailable_contract(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_background_unavailable_contract_schema(),
    )


def _fallback_path_status(fallback_policy: str | None) -> str:
    if fallback_policy == "deterministic_base_path":
        return "deterministic_base_path_available"
    if fallback_policy == "local_worker":
        return "local_worker_available"
    if fallback_policy == "manual_review":
        return "manual_review_available"
    return "fallback_policy_unavailable"


def build_hermes_background_unavailable_lease_result(
    *,
    lease_request: Mapping[str, Any],
    unavailable_kind: str,
    reason_code: str | None = None,
    captured_task_ref: str | None = None,
    worker_ref: str | None = None,
    evidence_refs: Sequence[str] = (HERMES_BACKGROUND_RESULT_CONTRACT_REF,),
    producer_role: str = "hermes_background_unavailable_contract",
) -> dict[str, Any]:
    """Build a typed non-completed Hermes background lease result.

    This contract is runner-facing: each unavailable/declined/blocked state has
    a distinct kind, outcome, fault domain, and fallback-path status. It never
    asks for credentials and never treats provider unavailability as an
    OpenYggdrasil runtime failure.
    """

    validate_reasoning_lease_request(lease_request)
    if unavailable_kind not in UNAVAILABLE_KIND_DEFINITIONS:
        raise ValueError(f"unknown Hermes background unavailable kind: {unavailable_kind}")

    definition = UNAVAILABLE_KIND_DEFINITIONS[unavailable_kind]
    fallback_policy = lease_request.get("fallback_policy")
    lease_status = definition["lease_status"]
    output = {
        "schema_version": "hermes_background_unavailable_contract.v1",
        "unavailable_id": uuid.uuid4().hex,
        "provider_id": lease_request.get("provider_id"),
        "provider_profile": lease_request.get("provider_profile"),
        "provider_session_id": lease_request.get("provider_session_id"),
        "unavailable_kind": unavailable_kind,
        "reason_code": reason_code or definition["reason_code"],
        "lease_status_decision": lease_status,
        "runner_outcome": definition["runner_outcome"],
        "fault_domain": definition["fault_domain"],
        "openyggdrasil_runtime_failure": False,
        "fallback_policy": fallback_policy,
        "fallback_path_status": _fallback_path_status(fallback_policy if isinstance(fallback_policy, str) else None),
        "deterministic_base_path_preserved": fallback_policy == "deterministic_base_path",
        "manual_review_path_preserved": fallback_policy == "manual_review",
        "captured_task_ref": captured_task_ref,
        "worker_ref": worker_ref,
        "sandbox_or_security_status": (
            "unavailable" if unavailable_kind == "sandbox_security_unavailable" else "not_applicable"
        ),
        "credential_prompted": False,
        "oauth_prompted": False,
        "raw_transcript_copied": False,
        "raw_session_copied": False,
        "state_db_result_harvested": False,
        "foreground_context_appended": False,
        "source_refs": [str(ref) for ref in evidence_refs][:32],
        "next_action": P4_H5_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_background_unavailable_contract(output)

    result = {
        "schema_version": "reasoning_lease_result.v1",
        "lease_result_id": uuid.uuid4().hex,
        "lease_request_id": lease_request["lease_request_id"],
        "lease_status": lease_status,
        "producer_role": producer_role,
        "provider_id": lease_request.get("provider_id"),
        "provider_profile": lease_request.get("provider_profile"),
        "provider_session_id": lease_request.get("provider_session_id"),
        "worker_ref": worker_ref,
        "fallback_used": False,
        "output": output,
        "confidence_score": 1.0,
        "failure_reason": output["reason_code"],
        "completed_at": utc_now_iso(),
    }
    validate_reasoning_lease_result(result)
    return result
