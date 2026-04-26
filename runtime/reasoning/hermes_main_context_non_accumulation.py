from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

HERMES_STATE_METADATA_POLICY_REF = (
    "private-evidence://core/2026-04-25/"
    "2026-04-25_phase-4-hermes-state-metadata-only-policy.md"
)
HERMES_BACKGROUND_RESULT_CONTRACT_REF = (
    "private-evidence://core/2026-04-25/"
    "2026-04-25_phase-4-hermes-background-result-contract.md"
)

P4_S1_ACTION = "P4.S1.provider-declined-runner-visibility"

OBSERVED_SURFACES = {
    "typed_gateway_result_surface",
    "bounded_preview",
    "digest",
    "source_ref",
    "task_ref",
    "explicit_unavailable",
    "provider_state_metadata_ref",
    "static_reference_marker",
}

BLOCKED_ATTEMPTS = {
    "attempted_foreground_context_append": (
        "foreground_context_append",
        "foreground_context_append_not_allowed",
    ),
    "attempted_raw_worker_prompt_copy": (
        "raw_worker_prompt_copy",
        "raw_worker_prompt_copy_not_allowed",
    ),
    "attempted_raw_worker_trace_copy": (
        "raw_worker_trace_copy",
        "raw_worker_trace_copy_not_allowed",
    ),
    "attempted_raw_tool_output_copy": (
        "raw_tool_output_copy",
        "raw_tool_output_copy_not_allowed",
    ),
    "attempted_raw_lease_result_payload_copy": (
        "raw_lease_result_payload_copy",
        "raw_lease_result_payload_copy_not_allowed",
    ),
}


@lru_cache(maxsize=1)
def load_hermes_main_context_non_accumulation_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_main_context_non_accumulation.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_main_context_non_accumulation(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_main_context_non_accumulation_schema(),
    )


def _unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _valid_surfaces(values: Sequence[str]) -> list[str]:
    surfaces = [str(value) for value in values if str(value) in OBSERVED_SURFACES]
    return _unique(surfaces)


def _bounded_material_policy_ok(
    *,
    bounded_preview_used: bool,
    digest_used: bool,
    source_ref_used: bool,
    observed_surfaces: Sequence[str],
) -> bool:
    if "explicit_unavailable" in observed_surfaces:
        return True
    return bounded_preview_used and digest_used and source_ref_used


def build_hermes_main_context_non_accumulation_proof(
    *,
    provider_id: str = "hermes",
    provider_profile: str = "default",
    provider_session_id: str = "unknown",
    evidence_mode: str = "static_reference_marker",
    live_history_diff_available: bool = False,
    static_reference_non_append_marker_present: bool = False,
    observed_surfaces: Sequence[str] = (
        "static_reference_marker",
        "bounded_preview",
        "digest",
        "source_ref",
    ),
    bounded_preview_used: bool = True,
    digest_used: bool = True,
    source_ref_used: bool = True,
    attempted_foreground_context_append: bool = False,
    attempted_raw_worker_prompt_copy: bool = False,
    attempted_raw_worker_trace_copy: bool = False,
    attempted_raw_tool_output_copy: bool = False,
    attempted_raw_lease_result_payload_copy: bool = False,
    evidence_refs: Sequence[str] = (
        HERMES_STATE_METADATA_POLICY_REF,
        HERMES_BACKGROUND_RESULT_CONTRACT_REF,
    ),
) -> dict[str, Any]:
    """Build a typed foreground-context non-accumulation proof.

    The proof is scoped to OpenYggdrasil's runner/lease boundary. It records
    static or live evidence that worker prompts, traces, raw tool outputs, and
    lease result payloads are not appended to a provider's main foreground
    conversation. When evidence is insufficient, it emits typed unavailable
    instead of claiming success.
    """

    surfaces = _valid_surfaces(observed_surfaces)
    if not surfaces:
        surfaces = ["explicit_unavailable"]

    attempt_flags = {
        "attempted_foreground_context_append": attempted_foreground_context_append,
        "attempted_raw_worker_prompt_copy": attempted_raw_worker_prompt_copy,
        "attempted_raw_worker_trace_copy": attempted_raw_worker_trace_copy,
        "attempted_raw_tool_output_copy": attempted_raw_tool_output_copy,
        "attempted_raw_lease_result_payload_copy": attempted_raw_lease_result_payload_copy,
    }

    blocked_attempts: list[str] = []
    reason_codes: list[str] = []
    unsafe_attempt_present = False
    for flag_name, attempted in attempt_flags.items():
        if attempted:
            attempt_kind, reason_code = BLOCKED_ATTEMPTS[flag_name]
            blocked_attempts.append(attempt_kind)
            reason_codes.append(reason_code)
            unsafe_attempt_present = True

    bounded_policy_ok = _bounded_material_policy_ok(
        bounded_preview_used=bounded_preview_used,
        digest_used=digest_used,
        source_ref_used=source_ref_used,
        observed_surfaces=surfaces,
    )
    if not bounded_policy_ok:
        blocked_attempts.append("missing_bounded_result_policy")
        reason_codes.append("missing_bounded_result_policy")

    if unsafe_attempt_present:
        proof_status = "blocked_unsafe_surface"
        foreground_append_status = "blocked"
    elif not bounded_policy_ok:
        proof_status = "typed_unavailable"
        foreground_append_status = "typed_unavailable"
    elif evidence_mode == "live_history_diff":
        if live_history_diff_available:
            proof_status = "live_history_diff_proven"
            foreground_append_status = "not_appended"
            reason_codes.append("main_context_non_accumulation_live_history_diff_proven")
        else:
            proof_status = "typed_unavailable"
            foreground_append_status = "typed_unavailable"
            reason_codes.append("live_history_diff_unavailable")
    elif evidence_mode == "static_reference_marker":
        if static_reference_non_append_marker_present:
            proof_status = "static_reference_proven"
            foreground_append_status = "not_appended"
            reason_codes.append("main_context_non_accumulation_static_reference_proven")
        else:
            proof_status = "typed_unavailable"
            foreground_append_status = "typed_unavailable"
            reason_codes.append("static_non_append_marker_unavailable")
    else:
        proof_status = "typed_unavailable"
        foreground_append_status = "typed_unavailable"
        reason_codes.append("main_context_non_accumulation_evidence_unavailable")

    payload = {
        "schema_version": "hermes_main_context_non_accumulation.v1",
        "proof_id": uuid.uuid4().hex,
        "provider_id": str(provider_id),
        "provider_profile": str(provider_profile),
        "provider_session_id": str(provider_session_id),
        "proof_status": proof_status,
        "foreground_append_status": foreground_append_status,
        "evidence_mode": evidence_mode if evidence_mode in {"static_reference_marker", "live_history_diff"} else "typed_unavailable",
        "reason_codes": _unique(reason_codes),
        "observed_surfaces": surfaces[:12],
        "live_history_diff_available": bool(live_history_diff_available),
        "static_reference_non_append_marker_present": bool(static_reference_non_append_marker_present),
        "worker_prompts_appended": False,
        "worker_traces_appended": False,
        "raw_tool_outputs_appended": False,
        "lease_result_payloads_appended": False,
        "raw_worker_prompt_copied": False,
        "raw_worker_trace_copied": False,
        "raw_tool_output_copied": False,
        "raw_lease_result_payload_copied": False,
        "bounded_preview_used": bool(bounded_preview_used),
        "digest_used": bool(digest_used),
        "source_ref_used": bool(source_ref_used),
        "blocked_attempt_kinds": _unique(blocked_attempts),
        "source_refs": [str(ref) for ref in evidence_refs][:32],
        "next_action": P4_S1_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_main_context_non_accumulation(payload)
    return payload
