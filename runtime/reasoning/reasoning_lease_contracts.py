from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping

import jsonschema

from reasoning.provider_capability_descriptor import background_reasoning_descriptor_implies_completed_support


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

REASONING_DEPTH_ORDER = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "xhigh": 4,
}
REASONING_DEPTH_AREAS = {
    "foreground_truth",
    "typed_availability",
    "privacy_leak",
    "freshness_lifecycle",
    "conflict_correction",
    "retrieval_relevance",
    "mailbox_quality",
    "graph_cache_authority",
    "response_quality",
    "evidence_pointer",
    "reasoning_lease",
    "provider_resource_boundary",
    "general_background_reasoning",
}
REASONING_ENERGY_SOURCES = {
    "deterministic_contract",
    "codex_development_loop",
    "provider_headless",
    "local_worker",
    "manual_review",
}
REASONING_DEPTH_EVIDENCE = {
    "schema_valid_request",
    "red_green_proof",
    "typed_unavailable",
    "run_record",
    "scorecard_metric",
    "provider_descriptor",
    "sandbox_decision",
}


def _load_schema(filename: str) -> Dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_reasoning_lease_request_schema() -> Dict[str, Any]:
    return _load_schema("reasoning_lease_request.v1.schema.json")


@lru_cache(maxsize=1)
def load_reasoning_lease_result_schema() -> Dict[str, Any]:
    return _load_schema("reasoning_lease_result.v1.schema.json")


def validate_reasoning_lease_request(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_reasoning_lease_request_schema())


def validate_reasoning_lease_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_reasoning_lease_result_schema())


def build_reasoning_depth_requirement(
    *,
    area: str,
    minimum_depth: str,
    requested_depth: str | None = None,
    depth_status: str = "required",
    reasoning_energy_source: str = "provider_headless",
    escalation_policy: str = "lease_required",
    downgrade_policy: str = "forbid",
    evidence_required: tuple[str, ...] = ("schema_valid_request", "provider_descriptor"),
    reason_codes: tuple[str, ...] = ("structured_reasoning_depth_required",),
) -> dict[str, Any]:
    """Build the structured reasoning-depth requirement for a lease request.

    Reasoning depth must not be exchanged as free-form text in the objective.
    The lease request schema requires this object and fixes
    plain_text_depth_request_allowed to false.
    """

    if area not in REASONING_DEPTH_AREAS:
        raise ValueError(f"unknown reasoning depth area: {area}")
    if minimum_depth not in REASONING_DEPTH_ORDER:
        raise ValueError(f"unknown minimum reasoning depth: {minimum_depth}")
    requested = requested_depth or minimum_depth
    if requested not in REASONING_DEPTH_ORDER:
        raise ValueError(f"unknown requested reasoning depth: {requested}")
    if REASONING_DEPTH_ORDER[requested] < REASONING_DEPTH_ORDER[minimum_depth]:
        raise ValueError("requested_depth must meet or exceed minimum_depth")
    if depth_status not in {"required", "verified", "downgraded", "unavailable"}:
        raise ValueError(f"unknown reasoning depth status: {depth_status}")
    if reasoning_energy_source not in REASONING_ENERGY_SOURCES:
        raise ValueError(f"unknown reasoning energy source: {reasoning_energy_source}")
    invalid_evidence = set(evidence_required) - REASONING_DEPTH_EVIDENCE
    if invalid_evidence:
        raise ValueError(f"unknown reasoning depth evidence: {sorted(invalid_evidence)}")

    return {
        "schema_version": "reasoning_depth_requirement.v1",
        "area": area,
        "minimum_depth": minimum_depth,
        "requested_depth": requested,
        "depth_status": depth_status,
        "plain_text_depth_request_allowed": False,
        "reasoning_energy_source": reasoning_energy_source,
        "escalation_policy": escalation_policy,
        "downgrade_policy": downgrade_policy,
        "evidence_required": list(evidence_required),
        "reason_codes": list(reason_codes),
    }


def provider_supports_background_reasoning(provider_descriptor: Mapping[str, Any]) -> bool:
    return background_reasoning_descriptor_implies_completed_support(provider_descriptor)


def lease_mode_for_provider(provider_descriptor: Mapping[str, Any]) -> str:
    if provider_supports_background_reasoning(provider_descriptor):
        return "provider_headless"
    return "deterministic_base_path"
