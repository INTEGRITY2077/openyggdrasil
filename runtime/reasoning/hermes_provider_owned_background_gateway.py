from __future__ import annotations

import hashlib
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso
from reasoning.hermes_background_unavailable_contract import (
    build_hermes_background_unavailable_lease_result,
)
from reasoning.reasoning_lease_contracts import (
    validate_reasoning_lease_request,
    validate_reasoning_lease_result,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

GATEWAY_SURFACE_INVENTORY_REF = (
    "private-evidence://Dev_history/todo/worker1/2026-04-30/result/"
    "2026-04-30_1318_worker1_provider_owned_background_gateway_surface_inventory_result.md"
)

P4_H1_ACTION = "P4.H1.hermes-background-explicit-invocation-smoke"
P4_H2_ACTION = "P4.H2.hermes-background-task-id-capture"

UNSAFE_REASON_CODES = {
    "stdin_injection_attempted": "stdin_injection_not_allowed",
    "raw_prompt_copied": "raw_provider_prompt_copy_not_allowed",
    "raw_session_copied": "raw_provider_session_copy_not_allowed",
    "state_db_result_harvested": "state_db_result_harvesting_not_allowed",
    "foreground_context_appended": "foreground_context_append_not_allowed",
}


@lru_cache(maxsize=1)
def load_hermes_provider_owned_background_gateway_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_provider_owned_background_gateway.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_provider_owned_background_gateway(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_provider_owned_background_gateway_schema(),
    )


def _request_fingerprint(request: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(request), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _first_unsafe_reason(safety: Mapping[str, bool]) -> str | None:
    for flag_name, reason_code in UNSAFE_REASON_CODES.items():
        if safety.get(flag_name) is True:
            return reason_code
    return None


def build_hermes_provider_owned_background_gateway_contract(
    *,
    lease_request: Mapping[str, Any],
    gateway_available: bool = False,
    evidence_refs: Sequence[str] = (GATEWAY_SURFACE_INVENTORY_REF,),
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build the safe handoff contract for a provider-owned /background gateway.

    This does not call Hermes or any provider process. It only declares the
    typed handoff shape and fails closed when no provider-owned gateway is
    exposed. A live runner must satisfy this contract before Worker 2 can be
    retargeted.
    """

    request = dict(lease_request)
    validate_reasoning_lease_request(request)

    safety = {
        "stdin_injection_attempted": False,
        "raw_prompt_copied": False,
        "raw_session_copied": False,
        "state_db_result_harvested": False,
        "foreground_context_appended": False,
    }
    safety.update(dict(safety_flags or {}))
    unsafe_reason = _first_unsafe_reason(safety)

    if unsafe_reason is not None:
        gateway_status = "blocked_unsafe_request"
        reason_codes = [unsafe_reason]
        invocation_surface = "none"
        next_action = P4_H1_ACTION
    elif gateway_available:
        gateway_status = "ready_for_provider_gateway"
        reason_codes = [
            "provider_owned_background_gateway_contract_ready",
            "typed_task_id_and_context_window_proof_required",
        ]
        invocation_surface = "provider_owned_command_gateway"
        next_action = P4_H2_ACTION
    else:
        gateway_status = "typed_unavailable"
        reason_codes = ["provider_owned_background_gateway_not_exposed"]
        invocation_surface = "none"
        next_action = P4_H1_ACTION

    fingerprint = _request_fingerprint(request)
    payload = {
        "schema_version": "hermes_provider_owned_background_gateway.v1",
        "gateway_request_id": uuid.uuid4().hex,
        "lease_request_id": request["lease_request_id"],
        "provider_id": request.get("provider_id"),
        "provider_profile": request.get("provider_profile"),
        "provider_session_id": request.get("provider_session_id"),
        "gateway_status": gateway_status,
        "command": "/background",
        "invocation_surface": invocation_surface,
        "request_mode": "focused_background_request",
        "lease_request_ref": (
            "reasoning-lease-request-ref://openyggdrasil/"
            f"provider-owned-background-gateway/{fingerprint[:32]}"
        ),
        "request_fingerprint_sha256": fingerprint,
        "input_ref_count": len(dict(request.get("input_refs") or {})),
        "expected_task_id_prefix": "bg_",
        "typed_task_result_requirement": "typed_task_id_and_typed_result_or_typed_unavailable",
        "main_context_window_proof_requirement": "before_after_refs_or_equivalent_typed_proof",
        "provider_gateway_called": False,
        "stdin_injection_attempted": False,
        "raw_prompt_copied": False,
        "raw_session_copied": False,
        "state_db_result_harvested": False,
        "foreground_context_appended": False,
        "reason_codes": reason_codes,
        "source_refs": [str(ref) for ref in evidence_refs][:32],
        "next_action": next_action,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_provider_owned_background_gateway(payload)
    return payload


def build_hermes_provider_owned_background_gateway_unavailable_result(
    *,
    lease_request: Mapping[str, Any],
    worker_ref: str | None = None,
    evidence_refs: Sequence[str] = (GATEWAY_SURFACE_INVENTORY_REF,),
) -> dict[str, Any]:
    """Return typed unavailable when the provider-owned gateway is absent."""

    contract = build_hermes_provider_owned_background_gateway_contract(
        lease_request=lease_request,
        gateway_available=False,
        evidence_refs=evidence_refs,
    )
    result = build_hermes_background_unavailable_lease_result(
        lease_request=lease_request,
        unavailable_kind="handoff_gate_unavailable",
        reason_code="provider_owned_background_gateway_not_exposed",
        worker_ref=worker_ref,
        evidence_refs=[*evidence_refs, contract["lease_request_ref"]],
        producer_role="hermes_provider_owned_background_gateway",
    )
    validate_reasoning_lease_result(result)
    result["output"]["gateway_contract"] = contract
    validate_reasoning_lease_result(result)
    return result
