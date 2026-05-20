from __future__ import annotations

import hashlib

from runtime.wiki.operation import (
    build_index_entry,
    build_log_entry,
    build_source_cell,
    build_wiki_page_from_ring_node,
    lint_wiki_page_markdown,
    render_wiki_page_markdown,
    validate_support_bundle_v2,
)
from runtime.wiki.content_first_gate import evaluate_content_first_wiki_article


ANCHOR_HASH = hashlib.sha256(b"wiki-operation-contract-test").hexdigest()
SOURCE_REF = "hermes-session-json://wiki-operation-contract-test"
PAGE_REF = "oy-vault://categories/software-development/contracts/wiki-operation.md"


def _ring_node() -> dict:
    return {
        "node_id": "N-wiki-operation-contract-test",
        "canonical_topic": {
            "topic_id": "topic:wiki-operation-contract-test",
            "title": "Wiki operation contract separates page content from proof metadata",
        },
        "decision_capsule": {
            "decision": "Readable wiki pages should lead; proof metadata belongs in the machine appendix.",
            "context": "A user or LLM should understand the topic before seeing machine metadata.",
            "conclusion": "Keep raw source and source cell evidence attached but below the page body.",
            "forbidden": ["Do not treat evidence metadata as the page body."],
            "reuse_condition": "Use when rendering OpenYggdrasil wiki pages from source-backed memory.",
        },
        "provenance_rings": [
            {
                "ring_id": "ring-wiki-operation-contract-test",
                "source_ref": SOURCE_REF,
                "origin_locator": f"{SOURCE_REF}#message_index=0..3",
                "anchor_hash": ANCHOR_HASH,
            }
        ],
        "community": {
            "community_id": "community:wiki-operation",
        },
    }


def test_wiki_page_contract_renders_prose_first_markdown() -> None:
    cell = build_source_cell(
        raw_source_ref=SOURCE_REF,
        origin_locator=f"{SOURCE_REF}#message_index=0..3",
        supports=["Readable wiki pages should lead before proof metadata."],
        does_not_support=["full production readiness"],
        anchor_hash=ANCHOR_HASH,
    )
    page = build_wiki_page_from_ring_node(
        ring_node=_ring_node(),
        page_ref=PAGE_REF,
        source_cell_refs=[cell["source_cell_id"]],
        machine_appendix_ref=f"{PAGE_REF}#machine-appendix",
    )
    index_entry = build_index_entry(wiki_page=page, category_path="software-development/contracts")
    log_entry = build_log_entry(
        operation="ingest",
        summary="Rendered wiki operation contract page.",
        pages_touched=[PAGE_REF],
        source_ref=SOURCE_REF,
    )
    markdown = render_wiki_page_markdown(
        wiki_page=page,
        source_cells=[cell],
        machine_appendix={"index_entry": index_entry, "log_entry": log_entry},
    )
    assert "# Wiki operation contract separates page content from proof metadata" in markdown
    assert markdown.index("## What This Page Is") < markdown.index("## Machine Appendix")
    assert lint_wiki_page_markdown(markdown)["status"] == "pass"


def test_wiki_continent_renderer_keeps_lineage_contract_markers_in_machine_appendix() -> None:
    from runtime.operator.wiki_page_renderer import render_wiki_continent_page

    ring_node = _ring_node()
    ring_node["semantic_category_path"] = {
        "schema_version": "semantic_category_path.v1",
        "path": "software-development/contracts",
        "segments": ["software-development", "contracts"],
        "category_authority": {"owner": "amundsen"},
    }
    ring_node["provider_source_events"] = [
        {
            "schema_version": "provider_source_event.v1",
            "event_id": "pse-test",
            "source_ref": SOURCE_REF,
            "message_index_range": {"start": 0, "end": 3},
            "anchor_hash": ANCHOR_HASH,
        }
    ]
    ring_node["decision_timeline"] = [
        {
            "schema_version": "decision_timeline_event.v1",
            "timeline_event_id": "dte-test",
            "decision_owner": "ms",
            "event_kind": "storage_admission",
            "reason_codes": ["source_ref_resolved"],
        }
    ]
    ring_node["community_growth_events"] = [
        {
            "schema_version": "community_growth_event.v1",
            "growth_event_id": "cge-test",
            "event_kind": "attached",
            "community_id": "community:wiki-operation",
            "created_at": "2026-05-21T00:00:00+09:00",
        }
    ]
    markdown = render_wiki_continent_page(ring_node=ring_node)
    assert '"schema_version": "wiki_continent_page.v1"' in markdown
    assert '"schema_version": "provider_source_event.v1"' in markdown
    assert '"schema_version": "decision_timeline_event.v1"' in markdown
    assert '"schema_version": "semantic_category_path.v1"' in markdown
    assert '"schema_version": "community_growth_event.v1"' in markdown


def test_lint_blocks_proof_marker_before_machine_appendix() -> None:
    markdown = """# Bad Page

## What It Is
receipt id at the top is proof-first contamination.

## Why It Matters
x

## Key Points
- x

## Important Distinctions
- x

## Related Pages
- x

## Sources
- x

## Open Questions
- x

## Machine Appendix
{}
"""
    result = lint_wiki_page_markdown(markdown)
    assert result["status"] == "fail"
    assert "receipt" in result["proof_markers_in_body"]


def test_content_first_gate_accepts_article_heading_variants_before_machine_appendix() -> None:
    markdown = """---
schema_version: wiki_article.v1
article_role: representative_tree
---
# Domestic Dog Ecology

Dogs adapt to people through inherited behavior, daily routines, and the environment around them.

## What This Page Decides
This page separates ordinary dog ecology from adjacent welfare or urban wildlife questions.

## Why It Matters
The same walk can be an ecology question, a welfare question, or an urban wildlife question.

## Operating Rule
Keep behavior and environment in the ecology page; split care ethics and wildlife impact when they become the main decision.

## Examples
- Breed differences can stay as a child detail when they explain the ecology question.

## How This Changed Over Time
The page started with walking stress, then added breed variation and an urban ecology split boundary.

## Source Synthesis
The page combines conversation turns, dog behavior references, and adjacent welfare/ecology source cells.

## Related Pages
- Companion Animal Welfare
- Urban Animal Ecology

## Machine Appendix
{}
"""
    result = evaluate_content_first_wiki_article(
        markdown,
        path_hint="vault/categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
    )
    assert result["verdict"] == "pass"
    assert "machine_appendix_late" in result["reason_codes"]


def test_support_bundle_v2_requires_wiki_page_and_source_cell_refs() -> None:
    cell = build_source_cell(
        raw_source_ref=SOURCE_REF,
        origin_locator=f"{SOURCE_REF}#message_index=0..3",
        supports=["MF1 should return readable wiki page refs plus source cells."],
    )
    validate_support_bundle_v2(
        {
            "schema_version": "support_bundle.v2",
            "query_text": "What should MF1 return?",
            "wiki_page_refs": [PAGE_REF],
            "support_facts": ["Return readable wiki page sections and source cells."],
            "source_cell_refs": [cell["source_cell_id"]],
            "provider_rejudgment_brief": {
                "answerable": True,
                "brief": "Use the support only after matching it to the current question.",
                "limits": ["Not a provider answer by itself."],
            },
            "excluded_states": ["pending", "unsafe", "quarantined", "repair_needed"],
            "hard_nonclaims": ["provider_must_rejudge_against_the_current_question"],
        }
    )
