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
RESOLVED_STATUSES = {"closed", "equivalent_guard"}


@lru_cache(maxsize=1)
def load_provider_reasoning_gate_schema() -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / "provider_reasoning_gate.v1.schema.json").read_text(encoding="utf-8"))


def validate_provider_reasoning_gate(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_provider_reasoning_gate_schema())


def _carry_forward_item(*, source_item: str, status: str) -> dict[str, str]:
    return {
        "source_item": source_item,
        "status": status,
        "gate_policy": (
            "allows_provider_output"
            if status in RESOLVED_STATUSES
            else "blocks_provider_output_until_resolved"
        ),
    }


def build_phase4_provider_reasoning_gate(
    *,
    role_local_fallback_contracts_status: str = "carried_forward_required",
    role_boundary_inspection_output_status: str = "carried_forward_required",
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the Phase 4 guard inherited from the Phase 3 close review."""

    blocked_reason_codes: list[str] = []
    if role_local_fallback_contracts_status not in RESOLVED_STATUSES:
        blocked_reason_codes.append("phase3_role_local_fallback_contracts_unclosed")
    if role_boundary_inspection_output_status not in RESOLVED_STATUSES:
        blocked_reason_codes.append("phase3_role_boundary_inspection_output_unclosed")

    allowed = not blocked_reason_codes
    gate = {
        "schema_version": "provider_reasoning_gate.v1",
        "gate_id": uuid.uuid4().hex,
        "phase": "Phase 4. Provider-Owned Reasoning Channel",
        "status": "ready" if allowed else "blocked",
        "requested_capability": "background_reasoning",
        "provider_reasoning_output_allowed": allowed,
        "blocked_reason_codes": blocked_reason_codes,
        "carry_forward_items": {
            "role_local_fallback_contracts": _carry_forward_item(
                source_item="P3.S1.role-local-fallback-contracts",
                status=role_local_fallback_contracts_status,
            ),
            "role_boundary_inspection_output": _carry_forward_item(
                source_item="P3.S2.role-boundary-inspection-output",
                status=role_boundary_inspection_output_status,
            ),
        },
        "required_before_provider_output": [
            "P3.S1.role-local-fallback-contracts",
            "P3.S2.role-boundary-inspection-output",
        ],
        "evidence_refs": [str(ref) for ref in evidence_refs],
        "next_action": (
            "provider_reasoning_output_allowed"
            if allowed
            else "close_role_local_fallback_and_boundary_inspection_before_provider_output"
        ),
        "created_at": utc_now_iso(),
    }
    validate_provider_reasoning_gate(gate)
    return gate


def provider_reasoning_gate_allows_output(payload: Mapping[str, Any] | None) -> bool:
    if payload is None:
        return False
    validate_provider_reasoning_gate(payload)
    return bool(payload.get("provider_reasoning_output_allowed"))
