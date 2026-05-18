from __future__ import annotations

from typing import Any, Mapping


def lineage_quality_blockers(ring_node: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not ring_node.get("provider_source_events"):
        blockers.append("provider_source_events_missing")
    if not ring_node.get("decision_timeline"):
        blockers.append("decision_timeline_missing")
    category_path = ring_node.get("semantic_category_path")
    if not isinstance(category_path, Mapping) or not category_path.get("path"):
        blockers.append("semantic_category_path_missing")
    if not ring_node.get("community_growth_events"):
        blockers.append("community_growth_events_missing")
    if str((ring_node.get("node_taxonomy") or {}).get("continent") or "") == "concepts" and not category_path:
        blockers.append("concepts_used_as_user_facing_continent")
    return blockers


def assess_lineage_quality(ring_node: Mapping[str, Any]) -> dict[str, Any]:
    blockers = lineage_quality_blockers(ring_node)
    return {
        "schema_version": "multi_provider_lineage_quality.v1",
        "verdict": "pass" if not blockers else "needs_review",
        "reason_codes": blockers,
        "checks": {
            "provider_source_events_present": bool(ring_node.get("provider_source_events")),
            "decision_timeline_present": bool(ring_node.get("decision_timeline")),
            "semantic_category_path_present": bool((ring_node.get("semantic_category_path") or {}).get("path")),
            "community_growth_events_present": bool(ring_node.get("community_growth_events")),
            "graphify_not_category_sot": True,
        },
        "hard_nonclaims": [
            "lineage_quality_is_not_full_production_ready",
            "graphify_is_advisory_not_category_authority",
        ],
    }


__all__ = ["assess_lineage_quality", "lineage_quality_blockers"]
