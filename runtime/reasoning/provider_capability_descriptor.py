from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from attachments.provider_attachment import validate_provider_descriptor


HERMES_BACKGROUND_EVIDENCE_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_hermes-background-reasoning-lease-proposal-evaluation.md"
)


def build_hermes_background_candidate_descriptor(
    *,
    evidence_refs: Sequence[str] = (HERMES_BACKGROUND_EVIDENCE_REF,),
) -> dict[str, Any]:
    """Describe Hermes /background as an adapted candidate, not completed proof."""

    return {
        "capability": "background_reasoning",
        "provider_surface": "hermes_background_command",
        "support_status": "adapted_candidate",
        "live_proof_required": True,
        "completion_status": "not_proven",
        "invocation_surface": "provider_owned_command_gateway",
        "task_id_prefix": "bg_",
        "context_window_policy": "must_not_append_to_main_active_conversation",
        "raw_session_policy": "metadata_only_no_raw_session_copy",
        "credential_policy": "provider_owned_no_openyggdrasil_credentials",
        "evidence_refs": [str(ref) for ref in evidence_refs],
        "next_action": "P4.H1.hermes-background-explicit-invocation-smoke",
    }


def build_background_unavailable_descriptor(
    *,
    evidence_refs: Sequence[str] = (),
    next_action: str = "use_deterministic_base_path",
) -> dict[str, Any]:
    return {
        "capability": "background_reasoning",
        "provider_surface": "unavailable",
        "support_status": "unavailable",
        "live_proof_required": True,
        "completion_status": "unavailable",
        "invocation_surface": "none",
        "task_id_prefix": None,
        "context_window_policy": "not_applicable",
        "raw_session_policy": "not_applicable",
        "credential_policy": "provider_owned_no_openyggdrasil_credentials",
        "evidence_refs": [str(ref) for ref in evidence_refs],
        "next_action": next_action,
    }


def attach_background_reasoning_descriptor(
    provider_descriptor: Mapping[str, Any],
    background_descriptor: Mapping[str, Any],
) -> dict[str, Any]:
    descriptor = deepcopy(dict(provider_descriptor))
    capabilities = deepcopy(dict(descriptor.get("capabilities") or {}))
    capabilities["background_reasoning_descriptor"] = dict(background_descriptor)
    capabilities["background_reasoning"] = (
        background_descriptor.get("support_status") == "supported"
        and background_descriptor.get("completion_status") == "live_proven"
        and background_descriptor.get("live_proof_required") is False
    )
    descriptor["capabilities"] = capabilities
    validate_provider_descriptor(descriptor)
    return descriptor


def attach_hermes_background_candidate_descriptor(
    provider_descriptor: Mapping[str, Any],
    *,
    evidence_refs: Sequence[str] = (HERMES_BACKGROUND_EVIDENCE_REF,),
) -> dict[str, Any]:
    return attach_background_reasoning_descriptor(
        provider_descriptor,
        build_hermes_background_candidate_descriptor(evidence_refs=evidence_refs),
    )


def background_reasoning_descriptor_implies_completed_support(provider_descriptor: Mapping[str, Any]) -> bool:
    capabilities = provider_descriptor.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return False
    detail = capabilities.get("background_reasoning_descriptor")
    if not isinstance(detail, Mapping):
        return bool(capabilities.get("background_reasoning"))
    return (
        capabilities.get("background_reasoning") is True
        and detail.get("support_status") == "supported"
        and detail.get("completion_status") == "live_proven"
        and detail.get("live_proof_required") is False
    )
