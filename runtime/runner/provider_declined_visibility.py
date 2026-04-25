from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso
from reasoning.reasoning_lease_contracts import validate_reasoning_lease_result


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"

HERMES_BACKGROUND_UNAVAILABLE_CONTRACT_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_phase-4-hermes-background-unavailable-contract.md"
)

P4_S2_ACTION = "P4.S2.no-credential-prompt-regression"

KNOWN_RUNNER_OUTCOMES = {
    "provider_declined",
    "provider_unavailable",
    "provider_timeout",
    "provider_cancelled",
    "result_unavailable",
    "handoff_blocked",
    "handoff_unavailable",
    "effort_below_minimum",
    "effort_unverifiable",
    "lease_security_unavailable",
}

KNOWN_FAULT_DOMAINS = {
    "provider",
    "provider_result",
    "handoff_gate",
    "effort_policy",
    "lease_security",
    "fallback",
    "completed",
    "unknown",
}

KNOWN_FALLBACK_PATH_STATUSES = {
    "deterministic_base_path_available",
    "local_worker_available",
    "manual_review_available",
    "fallback_policy_unavailable",
    "not_applicable",
}


@lru_cache(maxsize=1)
def load_provider_declined_runner_visibility_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "provider_declined_runner_visibility.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_provider_declined_runner_visibility(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_provider_declined_runner_visibility_schema(),
    )


def _reason_code(lease_result: Mapping[str, Any], output: Mapping[str, Any]) -> str:
    reason = str(output.get("reason_code") or lease_result.get("failure_reason") or "").strip()
    return reason or "reason_code_unavailable"


def _fallback_path_status(output: Mapping[str, Any]) -> str:
    status = str(output.get("fallback_path_status") or "").strip()
    if status in KNOWN_FALLBACK_PATH_STATUSES:
        return status
    fallback_policy = output.get("fallback_policy")
    if fallback_policy == "deterministic_base_path":
        return "deterministic_base_path_available"
    if fallback_policy == "local_worker":
        return "local_worker_available"
    if fallback_policy == "manual_review":
        return "manual_review_available"
    return "not_applicable"


def _visibility_status(lease_result: Mapping[str, Any], output: Mapping[str, Any]) -> str:
    runner_outcome = str(output.get("runner_outcome") or "").strip()
    if runner_outcome in KNOWN_RUNNER_OUTCOMES:
        return runner_outcome

    lease_status = str(lease_result.get("lease_status") or "")
    if lease_status == "declined":
        return "provider_declined"
    if lease_status == "fallback_used":
        return "fallback_used"
    if lease_status == "completed":
        return "completed"
    return "failed_unknown"


def _runner_stop_status(visibility_status: str) -> str:
    if visibility_status == "completed":
        return "completed"
    if visibility_status == "fallback_used":
        return "fallback"
    return "stopped"


def _fault_domain(visibility_status: str, output: Mapping[str, Any]) -> str:
    fault_domain = str(output.get("fault_domain") or "").strip()
    if fault_domain in KNOWN_FAULT_DOMAINS:
        return fault_domain
    if visibility_status == "provider_declined":
        return "provider"
    if visibility_status == "fallback_used":
        return "fallback"
    if visibility_status == "completed":
        return "completed"
    return "unknown"


def build_provider_declined_runner_visibility(
    lease_result: Mapping[str, Any],
    *,
    evidence_refs: Sequence[str] = (HERMES_BACKGROUND_UNAVAILABLE_CONTRACT_REF,),
) -> dict[str, Any]:
    """Expose provider-declined lease results as a typed runner-visible state."""

    validate_reasoning_lease_result(lease_result)
    output = dict(lease_result.get("output") or {})
    source_lease_status = str(lease_result["lease_status"])
    runner_visibility_status = _visibility_status(lease_result, output)
    provider_declined_visible = runner_visibility_status == "provider_declined"
    reason_code = _reason_code(lease_result, output)

    payload = {
        "schema_version": "provider_declined_runner_visibility.v1",
        "visibility_id": uuid.uuid4().hex,
        "lease_request_id": str(lease_result["lease_request_id"]),
        "provider_id": lease_result.get("provider_id"),
        "provider_profile": lease_result.get("provider_profile"),
        "provider_session_id": lease_result.get("provider_session_id"),
        "source_lease_status": source_lease_status,
        "runner_visibility_status": runner_visibility_status,
        "runner_stop_status": _runner_stop_status(runner_visibility_status),
        "reason_code": reason_code,
        "fault_domain": _fault_domain(runner_visibility_status, output),
        "fallback_path_status": _fallback_path_status(output),
        "provider_declined_visible": provider_declined_visible,
        "decline_reason_preserved": provider_declined_visible and reason_code != "reason_code_unavailable",
        "generic_failure_collapsed": False,
        "provider_decline_hidden_as_generic_failure": False,
        "openyggdrasil_runtime_failure": False,
        "credential_prompted": False,
        "oauth_prompted": False,
        "raw_session_copied": False,
        "foreground_context_appended": False,
        "source_refs": [str(ref) for ref in evidence_refs][:32],
        "next_action": P4_S2_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_provider_declined_runner_visibility(payload)
    return payload
