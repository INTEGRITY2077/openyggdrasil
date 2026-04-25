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

HERMES_BACKGROUND_UNAVAILABLE_CONTRACT_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_phase-4-hermes-background-unavailable-contract.md"
)

P4_H6_ACTION = "P4.H6.main-context-window-non-accumulation-proof"

ALLOWED_VERIFICATION_SURFACES = {
    "typed_gateway_result_surface",
    "digest",
    "source_ref",
    "task_ref",
    "explicit_unavailable",
    "provider_state_metadata_ref",
}

RESULT_TEXT_SOURCES = {
    "typed_gateway_result_surface",
    "digest",
    "source_ref",
    "task_ref",
    "explicit_unavailable",
}

STATE_REF_KINDS = {
    "state_db",
    "state_file",
    "session_metadata",
    "provider_log_metadata",
    "other_provider_state",
}


@lru_cache(maxsize=1)
def load_hermes_state_metadata_policy_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_state_metadata_policy.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_state_metadata_policy(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_state_metadata_policy_schema(),
    )


def _unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _state_ref(value: Mapping[str, Any]) -> dict[str, str]:
    ref_kind = str(value.get("ref_kind") or "other_provider_state")
    if ref_kind not in STATE_REF_KINDS:
        ref_kind = "other_provider_state"
    return {
        "path_hint": str(value.get("path_hint") or "unknown-provider-state"),
        "ref_kind": ref_kind,
        "allowed_use": "metadata_source_ref_or_provenance_hint_only",
    }


def build_hermes_state_metadata_policy_result(
    *,
    provider_id: str = "hermes",
    provider_profile: str = "default",
    provider_session_id: str = "unknown",
    provider_state_refs: Sequence[Mapping[str, Any]] = (),
    verification_surfaces: Sequence[str] = ("explicit_unavailable",),
    result_text_source: str | None = "explicit_unavailable",
    attempted_state_result_harvest: bool = False,
    attempted_raw_state_payload_copy: bool = False,
    evidence_refs: Sequence[str] = (HERMES_BACKGROUND_UNAVAILABLE_CONTRACT_REF,),
) -> dict[str, Any]:
    """Enforce provider state as metadata/provenance only.

    Hermes local state such as state.db may be referenced as a path/source hint,
    but it is never accepted as result text. Result verification must come from
    typed gateway/result surfaces, digests, task/source refs, or explicit
    unavailable state.
    """

    surfaces = _unique([str(surface) for surface in verification_surfaces])
    blocked_attempts: list[str] = []
    reason_codes: list[str] = []

    unknown_surfaces = [surface for surface in surfaces if surface not in ALLOWED_VERIFICATION_SURFACES]
    if unknown_surfaces:
        blocked_attempts.append("unknown_verification_surface")
        reason_codes.append("unknown_verification_surface_blocked")

    if result_text_source not in RESULT_TEXT_SOURCES and result_text_source is not None:
        if result_text_source == "state_db":
            blocked_attempts.append("state_db_as_result_text")
            reason_codes.append("state_db_result_text_blocked")
        else:
            blocked_attempts.append("provider_state_as_result_text")
            reason_codes.append("provider_state_result_text_blocked")

    if attempted_state_result_harvest:
        blocked_attempts.append("state_db_as_result_text")
        reason_codes.append("state_db_result_harvest_blocked")

    if attempted_raw_state_payload_copy:
        blocked_attempts.append("raw_state_payload_copy")
        reason_codes.append("raw_state_payload_copy_blocked")

    if not surfaces:
        surfaces = ["explicit_unavailable"]
    valid_surfaces = [surface for surface in surfaces if surface in ALLOWED_VERIFICATION_SURFACES]
    if not valid_surfaces:
        valid_surfaces = ["explicit_unavailable"]

    policy_status = "reject" if blocked_attempts else "pass"
    if not reason_codes:
        reason_codes.append("provider_state_metadata_only_policy_enforced")

    payload = {
        "schema_version": "hermes_state_metadata_policy.v1",
        "policy_id": uuid.uuid4().hex,
        "provider_id": str(provider_id),
        "provider_profile": str(provider_profile),
        "provider_session_id": str(provider_session_id),
        "policy_status": policy_status,
        "reason_codes": _unique(reason_codes),
        "provider_state_refs": [_state_ref(ref) for ref in provider_state_refs][:16],
        "verification_surfaces": _unique(valid_surfaces)[:12],
        "result_text_source": result_text_source if result_text_source in RESULT_TEXT_SOURCES else None,
        "state_result_harvest_attempt_status": "blocked" if blocked_attempts else "not_attempted",
        "blocked_attempt_kinds": _unique(blocked_attempts),
        "provider_state_as_result_source": False,
        "state_db_result_harvested": False,
        "raw_state_payload_copied": False,
        "source_refs": [str(ref) for ref in evidence_refs][:32],
        "next_action": P4_H6_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_state_metadata_policy(payload)
    return payload
