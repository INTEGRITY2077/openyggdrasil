from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from runtime.common.contract_validation import validate_contract_payload


RAW_SOURCE_SCHEMA = "raw_source.v1.schema.json"
SOURCE_CELL_SCHEMA = "source_cell.v1.schema.json"
WIKI_PAGE_SCHEMA = "wiki_page.v1.schema.json"
WIKI_INDEX_ENTRY_SCHEMA = "wiki_index_entry.v1.schema.json"
WIKI_LOG_ENTRY_SCHEMA = "wiki_log_entry.v1.schema.json"
WIKI_INGEST_TICKET_SCHEMA = "wiki_ingest_ticket.v1.schema.json"
WIKI_PAGE_MUTATION_SCHEMA = "wiki_page_mutation.v1.schema.json"
SUPPORT_BUNDLE_V2_SCHEMA = "support_bundle.v2.schema.json"

REQUIRED_WIKI_SECTIONS = (
    "## What This Page Is",
    "## Why It Matters",
    "## Key Points",
    "## Operating Rule",
    "## Category Placement",
    "## Retrieval Surface",
    "## Examples",
    "## How This Changed",
    "## Source Synthesis",
    "## Important Distinctions",
    "## Related Pages",
    "## Wiki Operations",
    "## Data Gaps",
    "## Open Questions",
    "## Machine Appendix",
)

PROOF_FIRST_MARKERS = (
    "receipt",
    "produced_count",
    "quality verdict",
    "quality_assessment",
    "source_ref_status",
    "proof report",
    "storage_receipt",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strings(values: Iterable[Any]) -> list[str]:
    return [str(item).strip() for item in values if str(item).strip()]


def _unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def validate_raw_source(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, RAW_SOURCE_SCHEMA)


def validate_source_cell(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, SOURCE_CELL_SCHEMA)


def validate_wiki_page(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_PAGE_SCHEMA)


def validate_index_entry(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_INDEX_ENTRY_SCHEMA)


def validate_log_entry(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_LOG_ENTRY_SCHEMA)


def validate_wiki_ingest_ticket(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_INGEST_TICKET_SCHEMA)


def validate_wiki_page_mutation(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_PAGE_MUTATION_SCHEMA)


def validate_support_bundle_v2(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, SUPPORT_BUNDLE_V2_SCHEMA)


def build_source_cell(
    *,
    raw_source_ref: str,
    origin_locator: str,
    supports: Iterable[str],
    does_not_support: Iterable[str] | None = None,
    captured_at: str | None = None,
    anchor_hash: str | None = None,
    confidence: str = "medium",
) -> dict[str, Any]:
    payload = {
        "schema_version": "source_cell.v1",
        "source_cell_id": _stable_id("src-cell", raw_source_ref, origin_locator, list(supports)),
        "raw_source_ref": raw_source_ref,
        "origin_locator": origin_locator,
        "supports": _strings(supports),
        "does_not_support": _strings(does_not_support or []),
        "captured_at": captured_at or _now(),
        "anchor_hash": anchor_hash,
        "confidence": confidence,
        "hard_nonclaims": [
            "source_cell_is_not_a_wiki_page",
            "source_cell_support_is_claim_scoped_not_production_ready_evidence",
        ],
    }
    validate_source_cell(payload)
    return payload


def build_wiki_page_from_ring_node(
    *,
    ring_node: Mapping[str, Any],
    page_ref: str,
    source_cell_refs: Iterable[str],
    machine_appendix_ref: str,
) -> dict[str, Any]:
    topic = ring_node.get("canonical_topic") or {}
    capsule = ring_node.get("decision_capsule") or {}
    title = str(topic.get("title") or ring_node.get("node_id") or "Untitled wiki page").strip()
    context = str(capsule.get("context") or "").strip()
    decision = str(capsule.get("decision") or capsule.get("conclusion") or "").strip()
    reuse_condition = str(capsule.get("reuse_condition") or "").strip()
    forbidden = _strings(_as_list(capsule.get("forbidden")))
    related = []
    for rel in ring_node.get("related_pages") or []:
        if isinstance(rel, Mapping) and rel.get("page_ref"):
            related.append(
                {
                    "page_ref": str(rel.get("page_ref")),
                    "relation": str(rel.get("relation") or "related"),
                    "why_related": str(rel.get("why_related") or "Shares a reusable decision context."),
                }
            )
    community = ring_node.get("community") or {}
    retrieval_contract = ring_node.get("retrieval_contract") if isinstance(ring_node.get("retrieval_contract"), Mapping) else {}
    retrieval_terms = _unique_strings(
        [
            *_strings(retrieval_contract.get("retrieval_terms") or []),
            *_strings(retrieval_contract.get("keywords") or []),
        ]
    )
    timeline = [
        item
        for item in ring_node.get("decision_timeline") or []
        if isinstance(item, Mapping)
    ]
    growth = [
        item
        for item in ring_node.get("community_growth_events") or []
        if isinstance(item, Mapping)
    ]
    if not related and community.get("community_id"):
        related.append(
            {
                "page_ref": f"oy-vault://communities/{str(community.get('community_id')).replace(':', '/')}.md",
                "relation": "community_context",
                "why_related": "This page belongs to the same knowledge community.",
            }
        )
    timeline_summary = _timeline_summary(timeline)
    examples = _strings(
        [
            _example_from_decision(decision),
            _example_from_reuse_condition(reuse_condition),
        ]
    )
    payload = {
        "schema_version": "wiki_page.v1",
        "page_ref": page_ref,
        "canonical_title": title,
        "display_title": title,
        "what_it_is": decision or context or "A reusable OpenYggdrasil wiki topic.",
        "why_it_matters": context or reuse_condition or "Future providers can reuse this without rereading the full source.",
        "key_points": _unique_strings(
            [
                decision,
                reuse_condition,
                str(capsule.get("conclusion") or "").strip(),
            ]
        )
        or ["This page summarizes a reusable source-backed distinction."],
        "examples": examples or ["Use this page when the same distinction appears in a later conversation."],
        "time_direction": timeline_summary
        or "The page records an initial Provider source, an MS1 admission decision, and later category/community updates when they occur.",
        "community_growth_summary": _community_growth_summary(growth),
        "important_distinctions": forbidden
        or ["Keep adjacent topics separate until an accepted later source explicitly bridges them."],
        "retrieval_terms": retrieval_terms,
        "related_pages": related,
        "source_cell_refs": _strings(source_cell_refs),
        "open_questions": _strings(ring_node.get("open_questions") or []),
        "machine_appendix_ref": machine_appendix_ref,
        "hard_nonclaims": [
            "wiki_page_is_not_a_provider_answer",
            "wiki_page_is_not_a_receipt_or_production_ready_proof",
            "mf1_safe_recall_and_provider_rejudgment_still_apply",
        ],
    }
    validate_wiki_page(payload)
    return payload


def build_index_entry(
    *,
    wiki_page: Mapping[str, Any],
    category_path: str,
    updated_at: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "wiki_index_entry.v1",
        "page_ref": wiki_page["page_ref"],
        "canonical_title": wiki_page["canonical_title"],
        "category_path": category_path,
        "summary": wiki_page["what_it_is"],
        "updated_at": updated_at or _now(),
        "source_cell_refs": list(wiki_page.get("source_cell_refs") or []),
        "related_page_refs": [
            str(item.get("page_ref"))
            for item in wiki_page.get("related_pages") or []
            if isinstance(item, Mapping) and item.get("page_ref")
        ],
    }
    validate_index_entry(payload)
    return payload


def build_log_entry(
    *,
    operation: str,
    summary: str,
    pages_touched: Iterable[str],
    source_ref: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "wiki_log_entry.v1",
        "log_id": _stable_id("wiki-log", operation, summary, list(pages_touched), source_ref),
        "timestamp": timestamp or _now(),
        "operation": operation,
        "summary": summary,
        "pages_touched": _strings(pages_touched),
        "source_ref": source_ref,
        "hard_nonclaims": [
            "log_entry_records_an_operation_not_final_support",
        ],
    }
    validate_log_entry(payload)
    return payload


def render_wiki_page_markdown(
    *,
    wiki_page: Mapping[str, Any],
    source_cells: Iterable[Mapping[str, Any]] = (),
    machine_appendix: Mapping[str, Any] | None = None,
) -> str:
    validate_wiki_page(wiki_page)
    cell_rows = list(source_cells)
    for cell in cell_rows:
        validate_source_cell(cell)
    related = wiki_page.get("related_pages") or []
    open_questions = wiki_page.get("open_questions") or []
    lines = [
        "---",
        "schema_version: wiki_article.v1",
        "article_role: representative_tree",
        f"page_ref: {wiki_page['page_ref']}",
        f"title: {wiki_page['canonical_title']}",
        f"root_claim: {str(wiki_page['what_it_is']).replace(chr(10), ' ')}",
        "---",
        f"# {wiki_page['canonical_title']}",
        "",
        "## What This Page Is",
        str(wiki_page["what_it_is"]),
        "",
        "## Why It Matters",
        str(wiki_page["why_it_matters"]),
        "",
        "## Key Points",
        *[f"- {item}" for item in wiki_page.get("key_points") or []],
        "",
        "## Operating Rule",
        str((wiki_page.get("key_points") or [wiki_page.get("what_it_is")])[0]),
        "",
        "## Category Placement",
        _category_placement_text(machine_appendix=machine_appendix, wiki_page=wiki_page),
        "",
        "## Retrieval Surface",
        *_retrieval_surface_lines(wiki_page=wiki_page),
        "",
        "## Examples",
        *[f"- {item}" for item in wiki_page.get("examples") or []],
        "",
        "## How This Changed",
        str(wiki_page.get("time_direction") or "No time-direction summary has been accepted yet."),
        "",
        "## Source Synthesis",
        _source_synthesis_text(wiki_page=wiki_page, source_cells=cell_rows),
        "",
        "## Important Distinctions",
        *[f"- {item}" for item in wiki_page.get("important_distinctions") or []],
        "",
        "## Maintenance Notes",
        str(wiki_page.get("community_growth_summary") or "No accepted maintenance or community-growth note has been recorded yet."),
        "",
        "## Related Pages",
    ]
    if related:
        lines.extend(
            f"- {item.get('relation')}: {item.get('page_ref')} - {item.get('why_related')}"
            for item in related
            if isinstance(item, Mapping)
        )
    else:
        lines.append("- No related page has been accepted yet.")
    lines.extend(
        [
            "",
            "## Wiki Operations",
            "- Ingest: source cells are admitted with source_ref, origin locator, anchor hash, and message range before this page is written.",
            "- Query: MF1 may use this page only through safe_index_cursor membership and source-backed support matching.",
            "- Lint: Janitor must check stale, duplicate, conflict, unsafe, and repair-needed states before production support.",
            "- Index/log: index.md and log.md must track this page so Raw / Wiki / Schema and Ingest / Query / Lint stay aligned.",
            "",
            "## Data Gaps",
            "- This page does not prove the whole memory system is ready for release.",
            "- Human review, graph dedupe, or later contradiction repair may still change the page state.",
            "- Adjacent topics remain separate until a later source-backed update explicitly bridges them.",
        ]
    )
    lines.extend(["", "## Sources"])
    if cell_rows:
        for index, cell in enumerate(cell_rows, start=1):
            supports = "; ".join(str(item) for item in cell.get("supports") or [])
            lines.append(f"- Accepted source {index}: {supports}")
    else:
        lines.append("- No source cells attached.")
    lines.extend(["", "## Open Questions"])
    if open_questions:
        lines.extend(f"- {item}" for item in open_questions)
    else:
        lines.append("- None recorded.")
    lines.extend(
        [
            "",
            "## Machine Appendix",
            "```json",
            _json_block(machine_appendix or {"wiki_page": dict(wiki_page)}),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _category_placement_text(
    *,
    machine_appendix: Mapping[str, Any] | None,
    wiki_page: Mapping[str, Any],
) -> str:
    appendix = machine_appendix if isinstance(machine_appendix, Mapping) else {}
    category = appendix.get("semantic_category_path") if isinstance(appendix.get("semantic_category_path"), Mapping) else {}
    category_path = str(category.get("path") or "").strip()
    if not category_path:
        page_ref = str(wiki_page.get("page_ref") or "")
        marker = "oy-vault://categories/"
        if page_ref.startswith(marker):
            category_path = page_ref.removeprefix(marker).rsplit("/", 1)[0]
    if not category_path:
        return "No accepted category path has been attached yet; keep this page candidate-only for placement decisions."
    segments = [segment for segment in category_path.split("/") if segment]
    if not segments:
        return "No accepted category path has been attached yet; keep this page candidate-only for placement decisions."
    continent = segments[0]
    mountain = " / ".join(segments[:2]) if len(segments) >= 2 else continent
    forest = " / ".join(segments[:3]) if len(segments) >= 3 else mountain
    tree_area = category_path
    return (
        f"This page is filed under `{tree_area}`. "
        f"Continent: `{continent}`. Mountain: `{mountain}`. Forest: `{forest}`. "
        "Use this placement to decide whether a later source should attach here, become a child page, split as a sibling, or stay rejected."
    )


def _retrieval_surface_lines(*, wiki_page: Mapping[str, Any]) -> list[str]:
    terms = _strings(wiki_page.get("retrieval_terms") or [])
    if not terms:
        terms = _strings(wiki_page.get("key_points") or [])[:4]
    if not terms:
        return ["- No accepted retrieval terms yet; keep recall conservative."]
    return [f"- {term}" for term in terms[:12]]


def _timeline_summary(events: Iterable[Mapping[str, Any]]) -> str:
    rows = list(events)
    if not rows:
        return ""
    labels: list[str] = []
    for row in rows[:5]:
        owner = str(row.get("decision_owner") or row.get("owner") or "system")
        kind = str(row.get("decision_kind") or row.get("event_kind") or "decision")
        labels.append(f"{owner}:{kind}")
    return "Decision lineage so far: " + " -> ".join(labels) + "."


def _community_growth_summary(events: Iterable[Mapping[str, Any]]) -> str:
    rows = list(events)
    if not rows:
        return "No accepted community growth event yet."
    kinds = [str(row.get("event_kind") or "event") for row in rows[:5]]
    return "Community growth recorded as: " + ", ".join(kinds) + "."


def _example_from_decision(decision: str) -> str:
    text = str(decision or "").strip()
    if not text:
        return ""
    return f"When a later question asks this same distinction, start from: {text}"


def _example_from_reuse_condition(reuse_condition: str) -> str:
    text = str(reuse_condition or "").strip()
    if not text:
        return ""
    return f"Reuse condition: {text}"


def _source_synthesis_text(*, wiki_page: Mapping[str, Any], source_cells: Iterable[Mapping[str, Any]]) -> str:
    cells = list(source_cells)
    if not cells:
        return "No accepted source cell has been attached, so this page must stay candidate-only."
    supports: list[str] = []
    limits: list[str] = []
    for cell in cells:
        supports.extend(str(item).strip() for item in cell.get("supports") or [] if str(item).strip())
        limits.extend(str(item).strip() for item in cell.get("does_not_support") or [] if str(item).strip())
    support_text = supports[0] if supports else str(wiki_page.get("what_it_is") or "the page claim")
    return (
        "The accepted source material keeps this article grounded in the part of the conversation "
        "where the distinction stabilized. "
        f"It supports the reusable distinction that {support_text}. "
        "Nearby topics should still be split or bridged by later source-backed updates instead of by title similarity."
    )


def lint_wiki_page_markdown(markdown: str) -> dict[str, Any]:
    body, marker, _appendix = markdown.partition("## Machine Appendix")
    missing_sections = [section for section in REQUIRED_WIKI_SECTIONS if section not in markdown]
    proof_markers_in_body = [
        marker_text
        for marker_text in PROOF_FIRST_MARKERS
        if marker_text.lower() in body.lower()
    ]
    result = {
        "schema_version": "wiki_page_lint_result.v1",
        "status": "pass" if not missing_sections and not proof_markers_in_body and marker else "fail",
        "missing_sections": missing_sections,
        "proof_markers_in_body": proof_markers_in_body,
        "hard_nonclaims": [
            "lint_pass_is_not_live_ux_proof",
            "lint_pass_is_not_production_ready",
        ],
    }
    return result


__all__ = [
    "RAW_SOURCE_SCHEMA",
    "SOURCE_CELL_SCHEMA",
    "SUPPORT_BUNDLE_V2_SCHEMA",
    "WIKI_INDEX_ENTRY_SCHEMA",
    "WIKI_INGEST_TICKET_SCHEMA",
    "WIKI_LOG_ENTRY_SCHEMA",
    "WIKI_PAGE_MUTATION_SCHEMA",
    "WIKI_PAGE_SCHEMA",
    "build_index_entry",
    "build_log_entry",
    "build_source_cell",
    "build_wiki_page_from_ring_node",
    "lint_wiki_page_markdown",
    "render_wiki_page_markdown",
    "validate_index_entry",
    "validate_log_entry",
    "validate_raw_source",
    "validate_source_cell",
    "validate_support_bundle_v2",
    "validate_wiki_ingest_ticket",
    "validate_wiki_page",
    "validate_wiki_page_mutation",
]
