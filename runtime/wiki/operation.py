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
    "## What It Is",
    "## Why It Matters",
    "## Key Points",
    "## Important Distinctions",
    "## Related Pages",
    "## Sources",
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
    if not related and community.get("community_id"):
        related.append(
            {
                "page_ref": f"oy-vault://communities/{str(community.get('community_id')).replace(':', '/')}.md",
                "relation": "community_context",
                "why_related": "This page belongs to the same knowledge community.",
            }
        )
    payload = {
        "schema_version": "wiki_page.v1",
        "page_ref": page_ref,
        "canonical_title": title,
        "display_title": title,
        "what_it_is": decision or context or "A reusable OpenYggdrasil wiki topic.",
        "why_it_matters": context or reuse_condition or "Future providers can reuse this without rereading the full source.",
        "key_points": _strings(
            [
                decision,
                reuse_condition,
                str(capsule.get("conclusion") or "").strip(),
            ]
        )
        or ["This page summarizes a reusable source-backed distinction."],
        "important_distinctions": forbidden
        or ["Do not treat source-backed wiki support as a production-ready claim."],
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
        f"schema_version: {wiki_page['schema_version']}",
        f"page_ref: {wiki_page['page_ref']}",
        f"title: {wiki_page['canonical_title']}",
        "---",
        f"# {wiki_page['canonical_title']}",
        "",
        "## What It Is",
        str(wiki_page["what_it_is"]),
        "",
        "## Why It Matters",
        str(wiki_page["why_it_matters"]),
        "",
        "## Key Points",
        *[f"- {item}" for item in wiki_page.get("key_points") or []],
        "",
        "## Important Distinctions",
        *[f"- {item}" for item in wiki_page.get("important_distinctions") or []],
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
    lines.extend(["", "## Sources"])
    if cell_rows:
        for cell in cell_rows:
            supports = "; ".join(str(item) for item in cell.get("supports") or [])
            limits = "; ".join(str(item) for item in cell.get("does_not_support") or [])
            lines.append(f"- {cell['source_cell_id']}: {supports}")
            if limits:
                lines.append(f"  - Does not support: {limits}")
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
