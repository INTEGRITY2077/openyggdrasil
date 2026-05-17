from __future__ import annotations

import json
from typing import Any, Mapping

from runtime.common.contract_validation import validate_contract_payload
from runtime.memory.semantic_category_path import category_page_relative_path


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
    return f"""---
id: {ring_node['node_id']}
title: {topic['title']}
semantic_category_path: {category_path.get('path', '')}
community: {community.get('community_id', '')}
current_authority: active
---
# {topic['title']}

## What This Page Is
This is the production-facing wiki page for a source-backed OpenYggdrasil memory.

## Why It Matters
{capsule.get('context') or 'This topic may be reopened by another provider at a later time.'}

## Operating Rule
{capsule.get('conclusion') or capsule.get('decision') or ''}

## Category Placement
- semantic_category_path: {category_path.get('path', '')}
- category_authority: {(category_path.get('category_authority') or {}).get('owner', 'amundsen')}
- physical_storage_note: internal hash nodes are stable ids, not the user-facing continent.

## Provider Source Events
{_bullets(provider_events, key='event_id', fallback='no provider source events')}

## Decision Timeline
{_bullets(timeline, key='timeline_event_id', fallback='no decision timeline events')}

## Community Growth
{_bullets(growth, key='growth_event_id', fallback='no community growth events')}

## Source Synthesis
The page is backed by bounded provider source refs and may be enriched by external domain evidence. Graphify evidence is advisory and never the category authority.

## Retrieval Surface
- retrieval_terms: {', '.join(str(item) for item in retrieval.get('retrieval_terms') or retrieval.get('keywords') or [])}

## Maintenance Notes
- quality_verdict: {quality.get('verdict', 'unknown')}
- reason_codes: {', '.join(str(item) for item in quality.get('reason_codes') or [])}

## Machine Appendix

### Wiki Continent Page Contract
```json
{json.dumps(page_contract, ensure_ascii=False, indent=2)}
```

### Provider Source Events
```json
{json.dumps(provider_events, ensure_ascii=False, indent=2)}
```

### Decision Timeline
```json
{json.dumps(timeline, ensure_ascii=False, indent=2)}
```

### Semantic Category Path
```json
{json.dumps(category_path, ensure_ascii=False, indent=2)}
```

### Community Growth
```json
{json.dumps(growth, ensure_ascii=False, indent=2)}
```

### Ring Node Summary
```json
{json.dumps(ring_summary, ensure_ascii=False, indent=2, default=str)}
```
"""


def _bullets(rows: list[Any], *, key: str, fallback: str) -> str:
    lines: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            label = str(row.get(key) or row.get("schema_version") or "event")
            detail = str(row.get("decision_kind") or row.get("event_kind") or row.get("source_ref") or "")
            lines.append(f"- {label}: {detail}")
    return "\n".join(lines) if lines else f"- {fallback}"


def validate_wiki_continent_page_contract(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_CONTINENT_PAGE_SCHEMA)


__all__ = [
    "WIKI_CONTINENT_PAGE_SCHEMA",
    "render_wiki_continent_page",
    "validate_wiki_continent_page_contract",
]
