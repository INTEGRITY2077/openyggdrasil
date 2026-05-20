from __future__ import annotations

import json
from typing import Any, Mapping

from runtime.common.contract_validation import validate_contract_payload
from runtime.memory.semantic_category_path import category_page_relative_path
from runtime.wiki.operation import (
    build_index_entry,
    build_log_entry,
    build_source_cell,
    build_wiki_page_from_ring_node,
    lint_wiki_page_markdown,
    render_wiki_page_markdown,
)


WIKI_CONTINENT_PAGE_SCHEMA = "wiki_continent_page.v1.schema.json"


def render_wiki_continent_page(*, ring_node: Mapping[str, Any]) -> str:
    topic = ring_node["canonical_topic"]
    capsule = ring_node["decision_capsule"]
    category_path = ring_node.get("semantic_category_path") or {}
    provider_events = list(ring_node.get("provider_source_events") or [])
    timeline = list(ring_node.get("decision_timeline") or [])
    growth = list(ring_node.get("community_growth_events") or [])
    retrieval = ring_node.get("retrieval_contract") or {}
    community = ring_node.get("community") or {}
    quality = ring_node.get("quality_assessment") or {}
    segments = list(category_path.get("segments") or [])
    category_slug = segments[-1] if segments else str(topic.get("topic_id") or "page").split(":", 1)[-1]
    page_rel = category_page_relative_path(category_path, slug=category_slug)
    page_contract = {
        "schema_version": "wiki_continent_page.v1",
        "page_ref": f"oy-vault://{page_rel}",
        "internal_node_id": ring_node.get("node_id"),
        "semantic_category_path": category_path,
        "provider_source_events": provider_events,
        "decision_timeline": timeline,
        "community_growth_events": growth,
        "machine_appendix_present": True,
        "hard_nonclaims": [
            "wiki_page_is_not_provider_answer",
            "graphify_is_advisory_not_category_sot",
            "concept_mirror_is_internal_stable_id",
        ],
    }
    validate_wiki_continent_page_contract(page_contract)
    source_cells = _build_source_cells(ring_node=ring_node)
    wiki_page = build_wiki_page_from_ring_node(
        ring_node=ring_node,
        page_ref=f"oy-vault://{page_rel}",
        source_cell_refs=[cell["source_cell_id"] for cell in source_cells],
        machine_appendix_ref=f"oy-vault://{page_rel}#machine-appendix",
    )
    index_entry = build_index_entry(
        wiki_page=wiki_page,
        category_path=str(category_path.get("path") or ""),
    )
    log_entry = build_log_entry(
        operation="ingest",
        summary=f"Rendered wiki page: {topic['title']}",
        pages_touched=[wiki_page["page_ref"]],
        source_ref=source_cells[0]["raw_source_ref"] if source_cells else None,
    )
    ring_summary = {
        "schema_version": "wiki_ring_machine_summary.v1",
        "internal_node_id": ring_node.get("node_id"),
        "ring_ids": [str(item.get("ring_id") or "") for item in ring_node.get("provenance_rings") or [] if isinstance(item, Mapping)],
        "community_id": community.get("community_id"),
        "retrieval_terms": retrieval.get("retrieval_terms") or retrieval.get("keywords") or [],
        "quality_assessment": quality,
        "lineage_quality_assessment": ring_node.get("lineage_quality_assessment") or {},
        "hard_nonclaims": [
            "production_page_summary_omits_raw_resolver_paths",
            "internal_concept_mirror_contains_stable_machine_payload",
        ],
    }
    markdown = render_wiki_page_markdown(
        wiki_page=wiki_page,
        source_cells=source_cells,
        machine_appendix=_compact_machine_appendix(
            page_contract=page_contract,
            index_entry=index_entry,
            log_entry=log_entry,
            provider_events=provider_events,
            timeline=timeline,
            category_path=category_path,
            growth=growth,
            ring_summary=ring_summary,
        ),
    )
    lint = lint_wiki_page_markdown(markdown)
    return markdown.rstrip() + "\n\n<!-- wiki_page_lint_status: " + lint["status"] + " -->\n"


def _bullets(rows: list[Any], *, key: str, fallback: str) -> str:
    lines: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            label = str(row.get(key) or row.get("schema_version") or "event")
            detail = str(row.get("decision_kind") or row.get("event_kind") or row.get("source_ref") or "")
            lines.append(f"- {label}: {detail}")
    return "\n".join(lines) if lines else f"- {fallback}"


def _build_source_cells(*, ring_node: Mapping[str, Any]) -> list[dict[str, Any]]:
    topic = ring_node.get("canonical_topic") or {}
    capsule = ring_node.get("decision_capsule") or {}
    supports = [
        str(capsule.get("decision") or capsule.get("conclusion") or topic.get("title") or "").strip()
    ]
    does_not_support = [
        "claims outside the bounded source range",
        "nearby topics that only match by title similarity",
    ]
    cells: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    rings = [item for item in ring_node.get("provenance_rings") or [] if isinstance(item, Mapping)]
    if not rings:
        rings = [{"source_ref": f"oy-vault://internal/{ring_node.get('node_id', 'unknown')}", "origin_locator": "unknown"}]
    for ring in rings:
        raw_source_ref = str(ring.get("source_ref") or ring.get("raw_source_ref") or "")
        origin_locator = str(ring.get("origin_locator") or raw_source_ref)
        if not raw_source_ref:
            raw_source_ref = origin_locator or f"oy-vault://internal/{ring_node.get('node_id', 'unknown')}"
        dedupe_key = (
            raw_source_ref,
            origin_locator or raw_source_ref,
            str(ring.get("anchor_hash") or ""),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cells.append(
            build_source_cell(
                raw_source_ref=raw_source_ref,
                origin_locator=origin_locator or raw_source_ref,
                supports=supports or [str(topic.get("title") or "wiki page source support")],
                does_not_support=does_not_support,
                anchor_hash=ring.get("anchor_hash") if isinstance(ring.get("anchor_hash"), str) else None,
            )
        )
    return cells


def _compact_machine_appendix(
    *,
    page_contract: Mapping[str, Any],
    index_entry: Mapping[str, Any],
    log_entry: Mapping[str, Any],
    provider_events: list[Any],
    timeline: list[Any],
    category_path: Mapping[str, Any],
    growth: list[Any],
    ring_summary: Mapping[str, Any],
) -> dict[str, Any]:
    quality = ring_summary.get("quality_assessment") if isinstance(ring_summary.get("quality_assessment"), Mapping) else {}
    return {
        "schema_version": "wiki_page_machine_appendix.v1",
        "page_contract": {
            "schema_version": page_contract.get("schema_version"),
            "page_ref": page_contract.get("page_ref"),
            "machine_appendix_present": page_contract.get("machine_appendix_present"),
        },
        "page_ref": page_contract.get("page_ref"),
        "internal_node_id": page_contract.get("internal_node_id"),
        "index_ref": {
            "category_path": index_entry.get("category_path"),
            "updated_at": index_entry.get("updated_at"),
        },
        "log_ref": {
            "operation": log_entry.get("operation"),
            "timestamp": log_entry.get("timestamp"),
            "source_ref": log_entry.get("source_ref"),
        },
        "provider_source_events": [
            {
                "schema_version": event.get("schema_version") or "provider_source_event.v1",
                "event_id": event.get("event_id"),
                "source_ref": event.get("source_ref"),
                "message_index_range": event.get("message_index_range"),
                "anchor_hash": event.get("anchor_hash"),
            }
            for event in provider_events
            if isinstance(event, Mapping)
        ],
        "decision_timeline": [
            {
                "schema_version": event.get("schema_version") or "decision_timeline_event.v1",
                "timeline_event_id": event.get("timeline_event_id"),
                "decision_owner": event.get("decision_owner"),
                "event_kind": event.get("event_kind") or event.get("decision_kind"),
                "reason_codes": event.get("reason_codes") or [],
            }
            for event in timeline
            if isinstance(event, Mapping)
        ],
        "semantic_category_path": {
            "schema_version": category_path.get("schema_version") or "semantic_category_path.v1",
            "path": category_path.get("path"),
            "segments": category_path.get("segments") or [],
            "owner": (category_path.get("category_authority") or {}).get("owner")
            if isinstance(category_path.get("category_authority"), Mapping)
            else None,
        },
        "community_growth": [
            {
                "schema_version": event.get("schema_version") or "community_growth_event.v1",
                "growth_event_id": event.get("growth_event_id"),
                "event_kind": event.get("event_kind"),
                "community_id": event.get("community_id"),
                "created_at": event.get("created_at"),
            }
            for event in growth
            if isinstance(event, Mapping)
        ],
        "quality_summary": {
            "verdict": quality.get("verdict"),
            "confidence": quality.get("confidence"),
            "reason_codes": quality.get("reason_codes") or [],
            "hard_nonclaims": quality.get("hard_nonclaims") or [],
        },
        "hard_nonclaims": page_contract.get("hard_nonclaims") or [],
    }


def validate_wiki_continent_page_contract(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_CONTINENT_PAGE_SCHEMA)


__all__ = [
    "WIKI_CONTINENT_PAGE_SCHEMA",
    "render_wiki_continent_page",
    "validate_wiki_continent_page_contract",
]
