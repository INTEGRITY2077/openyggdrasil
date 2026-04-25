from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_engraved_seed,
    validate_gardener_routing_decision,
    validate_planting_decision,
)
from harness_common import DEFAULT_VAULT, utc_now_iso
from provenance.provenance_store import provenance_relative_path


def build_gardener_routing_decision(
    *,
    engraved_seed: Mapping[str, Any],
    planting_decision: Mapping[str, Any],
    vault_root: Path = DEFAULT_VAULT,
) -> dict[str, Any]:
    """Route a planting target to forest paths without category or semantic judgment."""

    validate_engraved_seed(engraved_seed)
    validate_planting_decision(planting_decision)
    if str(planting_decision["seed_id"]) != str(engraved_seed["seed_id"]):
        raise ValueError("planting_decision seed_id does not match engraved_seed")
    if str(planting_decision["candidate_id"]) != str(engraved_seed["candidate_id"]):
        raise ValueError("planting_decision candidate_id does not match engraved_seed")

    active_vault_root = vault_root.resolve()
    canonical_relative_path = str(engraved_seed["canonical_relative_path"])
    provenance_rel = provenance_relative_path(topic_id=str(engraved_seed["topic_id"]))
    route = {
        "schema_version": "gardener_routing_decision.v1",
        "routing_id": uuid.uuid4().hex,
        "planting_id": str(planting_decision["planting_id"]),
        "seed_id": str(engraved_seed["seed_id"]),
        "candidate_id": str(engraved_seed["candidate_id"]),
        "topic_id": str(engraved_seed["topic_id"]),
        "topic_title": str(engraved_seed["topic_title"]),
        "page_id": str(engraved_seed["page_id"]),
        "forest_route_kind": "topic_page_with_provenance",
        "canonical_relative_path": canonical_relative_path,
        "provenance_relative_path": provenance_rel,
        "canonical_note_path": str((active_vault_root / canonical_relative_path).resolve()),
        "provenance_note_path": str((active_vault_root / provenance_rel).resolve()),
        "planting_target_kind": str(planting_decision["planting_target_kind"]),
        "planting_target_key": str(planting_decision["planting_target_key"]),
        "gardener_authority": "forest_routing_only",
        "semantic_worth_authority": "not_gardener",
        "category_authority": "not_gardener",
        "placement_authority": "not_gardener",
        "route_status": "ready_for_cultivation",
        "reason_codes": ["gardener_forest_route", "topic_page_with_provenance"],
        "routed_at": utc_now_iso(),
    }
    validate_gardener_routing_decision(route)
    return route
