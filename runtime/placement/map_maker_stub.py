from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_amundsen_nursery_handoff,
    validate_cultivated_decision,
    validate_gardener_routing_decision,
    validate_map_topography,
    validate_planting_decision,
)
from harness_common import utc_now_iso


def _field(payload: Mapping[str, Any], key: str) -> str:
    return str(payload[key])


def _assert_same(label: str, left: object, right: object) -> None:
    if str(left) != str(right):
        raise ValueError(f"map_maker_boundary_violation:{label}")


def _category_source_fields(
    *,
    amundsen_nursery_handoff: Mapping[str, Any] | None,
    planting_decision: Mapping[str, Any],
    cultivated_decision: Mapping[str, Any],
) -> dict[str, object]:
    if amundsen_nursery_handoff is None:
        return {
            "category_source": "planting_decision",
            "category_integrity_status": "legacy_planting_source_unverified",
            "amundsen_handoff_id": None,
        }
    validate_amundsen_nursery_handoff(amundsen_nursery_handoff)
    if amundsen_nursery_handoff["handoff_status"] != "ready_for_nursery":
        raise ValueError("map_maker_boundary_violation:amundsen_handoff_not_ready")
    topic_route = dict(amundsen_nursery_handoff["topic_route"])
    continent_route = dict(amundsen_nursery_handoff["continent_route"])
    _assert_same("continent_id_rewrite", continent_route["continent_id"], planting_decision["continent_id"])
    _assert_same("continent_key_rewrite", continent_route["continent_key"], planting_decision["continent_key"])
    _assert_same("topic_id_rewrite", topic_route["topic_id"], planting_decision["topic_id"])
    _assert_same("topic_title_rewrite", topic_route["topic_title"], planting_decision["topic_title"])
    _assert_same("cultivated_topic_id_rewrite", topic_route["topic_id"], cultivated_decision["topic_id"])
    _assert_same("page_id_rewrite", topic_route["page_id"], cultivated_decision["page_id"])
    _assert_same(
        "canonical_relative_path_rewrite",
        topic_route["canonical_relative_path"],
        cultivated_decision["canonical_relative_path"],
    )
    return {
        "category_source": "amundsen_nursery_handoff",
        "category_integrity_status": "verified_against_amundsen_handoff",
        "amundsen_handoff_id": str(amundsen_nursery_handoff["handoff_id"]),
    }


def _placement_source_fields(
    *,
    gardener_routing_decision: Mapping[str, Any] | None,
    cultivated_decision: Mapping[str, Any],
) -> dict[str, object]:
    if gardener_routing_decision is None:
        return {
            "placement_source": "cultivated_decision",
            "gardener_routing_id": None,
        }
    validate_gardener_routing_decision(gardener_routing_decision)
    if gardener_routing_decision["route_status"] != "ready_for_cultivation":
        raise ValueError("map_maker_boundary_violation:gardener_route_not_ready")
    _assert_same("placement_topic_id_rewrite", gardener_routing_decision["topic_id"], cultivated_decision["topic_id"])
    _assert_same("placement_page_id_rewrite", gardener_routing_decision["page_id"], cultivated_decision["page_id"])
    _assert_same(
        "placement_canonical_path_rewrite",
        gardener_routing_decision["canonical_relative_path"],
        cultivated_decision["canonical_relative_path"],
    )
    _assert_same(
        "placement_target_kind_rewrite",
        gardener_routing_decision["planting_target_kind"],
        cultivated_decision["planting_target_kind"],
    )
    _assert_same(
        "placement_target_key_rewrite",
        gardener_routing_decision["planting_target_key"],
        cultivated_decision["planting_target_key"],
    )
    return {
        "placement_source": "gardener_routing_decision",
        "gardener_routing_id": str(gardener_routing_decision["routing_id"]),
    }


def update_map_topography(
    *,
    planting_decision: Mapping[str, object],
    cultivated_decision: Mapping[str, object],
    amundsen_nursery_handoff: Mapping[str, object] | None = None,
    gardener_routing_decision: Mapping[str, object] | None = None,
) -> dict[str, object]:
    validate_planting_decision(planting_decision)
    validate_cultivated_decision(cultivated_decision)
    category_source = _category_source_fields(
        amundsen_nursery_handoff=amundsen_nursery_handoff,
        planting_decision=planting_decision,
        cultivated_decision=cultivated_decision,
    )
    placement_source = _placement_source_fields(
        gardener_routing_decision=gardener_routing_decision,
        cultivated_decision=cultivated_decision,
    )
    topography = {
        "schema_version": "map_topography.v1",
        "topography_id": uuid.uuid4().hex,
        "cultivation_id": _field(cultivated_decision, "cultivation_id"),
        "planting_id": _field(planting_decision, "planting_id"),
        "continent_id": _field(planting_decision, "continent_id"),
        "continent_key": _field(planting_decision, "continent_key"),
        "topic_id": _field(cultivated_decision, "topic_id"),
        "topic_title": _field(cultivated_decision, "topic_title"),
        "page_id": _field(cultivated_decision, "page_id"),
        "canonical_relative_path": _field(cultivated_decision, "canonical_relative_path"),
        "bed_id": _field(planting_decision, "bed_id"),
        "planting_target_kind": _field(planting_decision, "planting_target_kind"),
        "planting_target_key": _field(planting_decision, "planting_target_key"),
        "routing_mode": "topic_page_only",
        "topography_status": "aligned",
        "map_maker_authority": "placement_only",
        "semantic_worth_authority": "not_map_maker",
        "category_authority": "not_map_maker",
        "bridge_topology_authority": "not_map_maker",
        "bridge_creation_allowed": False,
        **category_source,
        **placement_source,
        "adjacency_keys": [],
        "bridge_count": 0,
        "map_updated_at": utc_now_iso(),
    }
    validate_map_topography(topography)
    return topography
