from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_role_split_integration_result,
    validate_thin_worker_chain_result,
)
from harness_common import utc_now_iso


ROLE_SEQUENCE = [
    "distiller",
    "evaluator",
    "amundsen",
    "seedkeeper",
    "gardener",
    "map_maker",
    "postman",
]

REQUIRED_ARTIFACTS = [
    "decision_candidate_batch",
    "evaluator_verdict",
    "evaluator_amundsen_handoff",
    "admission_verdict",
    "amundsen_nursery_handoff",
    "seedkeeper_segment",
    "nursery_composition_input",
    "engraved_seed",
    "planting_decision",
    "gardener_routing_decision",
    "cultivated_decision",
    "map_topography",
]


def _artifact_present(artifacts: Mapping[str, Any], key: str) -> bool:
    return isinstance(artifacts.get(key), Mapping)


def _failure_reasons(*, required_artifacts: Mapping[str, bool], authority_checks: Mapping[str, bool]) -> list[str]:
    failures: list[str] = []
    for key, ok in required_artifacts.items():
        if not ok:
            failures.append(f"missing_artifact:{key}")
    for key, ok in authority_checks.items():
        if not ok:
            failures.append(f"authority_check_failed:{key}")
    return failures


def inspect_role_split_integration(*, chain_result: Mapping[str, Any]) -> dict[str, Any]:
    """Verify that the thin worker chain still integrates after role splitting."""

    validate_thin_worker_chain_result(chain_result)
    artifacts = dict(chain_result.get("artifacts") or {})
    role_sequence = [str(step.get("role")) for step in chain_result.get("role_steps") or [] if isinstance(step, Mapping)]
    batch = dict(artifacts.get("decision_candidate_batch") or {})
    evaluator_verdict = dict(artifacts.get("evaluator_verdict") or {})
    evaluator_handoff = dict(artifacts.get("evaluator_amundsen_handoff") or {})
    amundsen_handoff = dict(artifacts.get("amundsen_nursery_handoff") or {})
    seedkeeper_segment = dict(artifacts.get("seedkeeper_segment") or {})
    nursery_input = dict(artifacts.get("nursery_composition_input") or {})
    gardener_route = dict(artifacts.get("gardener_routing_decision") or {})
    map_topography = dict(artifacts.get("map_topography") or {})
    postman_handoff = dict(chain_result.get("postman_handoff") or {})

    required_artifacts = {key: _artifact_present(artifacts, key) for key in REQUIRED_ARTIFACTS}
    required_artifacts["postman_handoff"] = bool(postman_handoff)
    authority_checks = {
        "distiller_no_semantic_filter": batch.get("semantic_filtering_allowed") is False,
        "evaluator_semantic_worth_owner": (
            evaluator_verdict.get("decision_authority") == "deterministic_prefilter_only"
            and evaluator_handoff.get("semantic_worth_authority") == "evaluator_only"
        ),
        "amundsen_route_only": (
            amundsen_handoff.get("route_authority") == "amundsen_category_decision_only"
            and amundsen_handoff.get("semantic_worth_authority") == "not_amundsen"
            and amundsen_handoff.get("placement_authority") == "not_amundsen"
        ),
        "seedkeeper_source_ref_only": (
            seedkeeper_segment.get("segment_authority") == "deterministic_source_ref_preservation_only"
            and seedkeeper_segment.get("semantic_worth_authority") == "not_seedkeeper"
            and seedkeeper_segment.get("category_authority") == "not_seedkeeper"
        ),
        "nursery_composed_input_ready": (
            nursery_input.get("composition_status") == "ready_for_seed_composition"
            and nursery_input.get("semantic_worth_source") == "evaluator_verdict"
            and nursery_input.get("route_source") == "amundsen_nursery_handoff"
            and nursery_input.get("source_ref_source") == "seedkeeper_segment"
        ),
        "gardener_forest_routing_only": (
            gardener_route.get("gardener_authority") == "forest_routing_only"
            and gardener_route.get("semantic_worth_authority") == "not_gardener"
            and gardener_route.get("category_authority") == "not_gardener"
            and gardener_route.get("placement_authority") == "not_gardener"
        ),
        "map_maker_placement_only": (
            map_topography.get("map_maker_authority") == "placement_only"
            and map_topography.get("semantic_worth_authority") == "not_map_maker"
            and map_topography.get("category_authority") == "not_map_maker"
            and map_topography.get("bridge_topology_authority") == "not_map_maker"
            and map_topography.get("category_source") == "amundsen_nursery_handoff"
            and map_topography.get("placement_source") == "gardener_routing_decision"
            and map_topography.get("category_integrity_status") == "verified_against_amundsen_handoff"
            and map_topography.get("bridge_creation_allowed") is False
            and map_topography.get("bridge_count") == 0
            and map_topography.get("adjacency_keys") == []
        ),
        "postman_delivery_ready": postman_handoff.get("handoff_status") == "ready_for_mailbox_packet",
    }
    failures = _failure_reasons(
        required_artifacts=required_artifacts,
        authority_checks=authority_checks,
    )
    if role_sequence != ROLE_SEQUENCE:
        failures.append("role_sequence_mismatch")

    result = {
        "schema_version": "role_split_integration_result.v1",
        "integration_id": uuid.uuid4().hex,
        "chain_result_id": str(chain_result["chain_result_id"]),
        "status": "passed" if not failures and chain_result.get("status") == "completed" else "failed",
        "role_sequence": role_sequence,
        "required_artifacts": required_artifacts,
        "authority_checks": authority_checks,
        "failure_reasons": failures,
        "reason_codes": ["role_split_integration_checked"],
        "checked_at": utc_now_iso(),
    }
    validate_role_split_integration_result(result)
    return result
