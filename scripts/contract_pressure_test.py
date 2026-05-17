#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / "runtime"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.common.contract_validation import validate_contract_payload
from runtime.memory.semantic_category_path import build_semantic_category_path
from runtime.memory.tree_ring_snapshot import build_tree_ring_snapshot
from runtime.operator.community_growth_writer import build_community_growth_event
from runtime.operator.decision_timeline_writer import build_decision_timeline_event
from runtime.operator.memory_ticket_admission import admit_memory_ticket_payload
from runtime.operator.provider_source_event_writer import build_provider_source_event
from runtime.operator.wiki_page_renderer import validate_wiki_continent_page_contract
from runtime.reasoning.amundsen_category_judgment import build_amundsen_category_judgment
from runtime.reasoning.provider_skill_receipt_consumer import build_provider_skill_receipt_menu
from runtime.reasoning.skill_metadata_reader import build_skill_metadata_read
from runtime.reasoning.persona_loader import build_subagent_persona_manifest
from runtime.retrieval.ptc_retrieval_orchestrator import (
    validate_retrieval_candidate,
    validate_retrieval_candidate_set,
)


FORMER_SIGNBOARD_SCHEMAS = (
    "amundsen_category_judgment.v1.schema.json",
    "community_growth_event.v1.schema.json",
    "decision_timeline_event.v1.schema.json",
    "memory_ticket.v1.schema.json",
    "provenance_ring_node.v1.schema.json",
    "provider_skill_receipt_consumer.v1.schema.json",
    "provider_source_event.v1.schema.json",
    "retrieval_candidate.v1.schema.json",
    "retrieval_candidate_set.v1.schema.json",
    "semantic_category_path.v1.schema.json",
    "skill_metadata_reader.v1.schema.json",
    "subagent_persona_manifest.v1.schema.json",
    "tree_ring_snapshot.v1.schema.json",
    "wiki_continent_page.v1.schema.json",
)


ANCHOR_HASH = hashlib.sha256(b"openyggdrasil-contract-pressure-test").hexdigest()
SOURCE_REF = "hermes-session-json://contract-pressure-test"


def _memory_ticket() -> dict[str, Any]:
    return {
        "schema_version": "memory_ticket.v1",
        "source_ref": SOURCE_REF,
        "message_index_range": {"start": 0, "end": 3},
        "provider_session_id": "contract-pressure-test",
        "surface_reason": "Reusable boundary survived several turns.",
        "commit_watermark": "session:contract-pressure-test:3",
        "anchor_hash": ANCHOR_HASH,
        "intent_field": "decision/context/conclusion/evidence/reuse_condition",
        "decomposition_guard": "preserve_paragraph_intent_before_decision_atoms",
        "min_split_unit": "paragraph_intent",
        "why_not_atomic": "This keeps a reusable role boundary with evidence and later recall conditions.",
        "topic_hint": "contract pressure test",
        "category_community_hint": "openyggdrasil contract refinery pressure test community",
        "decision": "Public contracts must circulate through runtime validation.",
        "context": "The contract is public-facing and must not be only a schema_version label.",
        "conclusion": "Schema-file validation is required before calling it active.",
        "reuse_condition": "Use this when auditing public contract readiness.",
    }


def _provider_event() -> dict[str, Any]:
    return build_provider_source_event(
        provider_id="hermes",
        provider_profile="test",
        provider_session_id="contract-pressure-test",
        source_ref=SOURCE_REF,
        message_index_range={"start": 0, "end": 3},
        anchor_hash=ANCHOR_HASH,
    )


def _decision_timeline_event() -> dict[str, Any]:
    return build_decision_timeline_event(
        decision_owner="ms",
        decision_kind="storage_admission",
        provider_source_event_ref="pse-contract-pressure-test",
        previous_decision_ref=SOURCE_REF,
        new_decision_ref="ring:ring-contract-pressure-test",
        reason_codes=["source_ref_resolved", "schema_file_validated"],
    )


def _community_growth_event() -> dict[str, Any]:
    return build_community_growth_event(
        community_id="community:contract-pressure-test",
        event_kind="attached",
        provider_source_event_ref="pse-contract-pressure-test",
        decision_timeline_event_ref="dte-contract-pressure-test",
        topic_key="contract-pressure-test",
        reason_codes=["community_growth_event_validated"],
    )


def _semantic_category_path() -> dict[str, Any]:
    return build_semantic_category_path(
        {"topic_hint": "Claude Code agent placement boundary"},
        topic_title="Claude Code agent placement boundary",
        decision_ref="decision-ref://contract-pressure-test/category",
        basis_refs=["oy-vault://sources/contract-pressure-test.md"],
    )


def _retrieval_candidate() -> dict[str, Any]:
    candidate = {
        "schema_version": "retrieval_candidate.v1",
        "candidate_id": "cand:contract-pressure-test",
        "generator": "bm25",
        "node_id": "N-contract-pressure-test",
        "source_path": "vault/categories/software-development/claude-code/agents.md",
        "source_ref": "oy-vault://categories/software-development/claude-code/agents.md",
        "origin_locator": "oy-vault://sources/contract-pressure-test.md#L1-L5",
        "line_range": {"start": 1, "end": 5},
        "community_id": "community:contract-pressure-test",
        "ring_id": "ring-contract-pressure-test",
        "lifecycle_state": "ACTIVE",
        "score": 0.9,
        "freshness": "current",
        "evidence_class": "source_path",
        "supporting_generators": ["bm25"],
        "rejection_reason": None,
    }
    validate_retrieval_candidate(candidate)
    return candidate


def _retrieval_candidate_set() -> dict[str, Any]:
    candidate = _retrieval_candidate()
    candidate_set = {
        "schema_version": "retrieval_candidate_set.v1",
        "query_text": "contract pressure test",
        "generated_at": "2026-05-17T00:00:00+00:00",
        "domain_hints": ["documentation_placement"],
        "generators_attempted": ["bm25"],
        "generator_reports": [
            {"generator": "bm25", "status": "completed", "candidate_count": 1, "reason": None}
        ],
        "merge_strategy": "dedupe_by_ring_node_source_then_feature_rerank",
        "reranker_policy": {"hard_gate_precedes_score": True},
        "candidates": [candidate],
        "selected_candidate_ids": [candidate["candidate_id"]],
        "rejected_candidate_ids": [],
        "coverage_state": "present",
        "retry_decision": {
            "status": "not_required",
            "attempts_used": 1,
            "max_attempts": 5,
            "reason": "source_backed_candidate_selected",
        },
    }
    validate_retrieval_candidate_set(candidate_set)
    return candidate_set


def _provenance_ring_node() -> dict[str, Any]:
    payload = {
        "schema_version": "provenance_ring_node.v1",
        "node_id": "N-contract-pressure-test",
        "canonical_topic": {
            "topic_id": "topic:contract-pressure-test",
            "title": "Contract pressure test",
            "page_path": "categories/software-development/contracts/pressure-test.md",
        },
        "decision_capsule": {
            "decision": "Public contracts must be schema-file validated.",
            "context": "A visible contract without runtime validation is a signboard pipe.",
            "conclusion": "Move it to active flow or demote it.",
            "evidence": [SOURCE_REF],
            "forbidden": ["production-ready self-claim"],
            "reuse_condition": "Use during contract refinery audits.",
        },
        "provenance_rings": [
            {
                "ring_id": "ring-contract-pressure-test",
                "source_ref": SOURCE_REF,
                "origin_locator": f"{SOURCE_REF}#message_index=0..3",
                "provider_session_id": "contract-pressure-test",
                "message_index_range": {"start": 0, "end": 3},
                "anchor_hash": ANCHOR_HASH,
                "commit_watermark": "session:contract-pressure-test:3",
                "surface_reason": "contract pressure test",
            }
        ],
        "lifecycle": {
            "state": "ACTIVE",
            "created_by_ring_id": "ring-contract-pressure-test",
            "lineage_edges": [{"type": "DERIVES_FROM", "target": SOURCE_REF}],
        },
        "community": {
            "community_id": "community:contract-pressure-test",
            "placement_reason": "contract pressure test",
            "related_nodes": [],
        },
        "retrieval_contract": {
            "keywords": ["contract", "pressure test"],
            "support_lanes": ["origin", "source_paths"],
        },
    }
    validate_contract_payload(payload, "provenance_ring_node.v1.schema.json")
    return payload


def _amundsen_category_judgment() -> dict[str, Any]:
    basis_ref = "oy-vault://sources/contract-pressure-test.md"
    return build_amundsen_category_judgment(
        category_request={
            "category_request_id": "category-request:contract-pressure-test",
            "candidate_ref": "oy-vault://candidates/contract-pressure-test",
            "basis_refs": [basis_ref],
            "category_candidates": [
                {
                    "category_ref": "oy-vault://categories/software-development/contracts",
                    "category_label": "software-development/contracts",
                    "basis_ref": basis_ref,
                    "confidence": 0.9,
                    "decision_branch": "existing_category",
                }
            ],
        }
    )


def _skill_metadata_read() -> dict[str, Any]:
    return build_skill_metadata_read(
        skill_ref="skill-ref://openyggdrasil/test-skill",
        frontmatter_ref="frontmatter-ref://openyggdrasil/test-skill",
        skill_source="---\nname: test-skill\ndescription: Contract pressure test\n---\nbody must not be read",
    )


def _provider_skill_receipt_menu() -> dict[str, Any]:
    return build_provider_skill_receipt_menu(
        receipt_consumer_request={
            "production_request_ref": "receipt-ref://openyggdrasil/request/1",
            "production_receipt_ref": "receipt-ref://openyggdrasil/receipt/1",
            "support_bundle_ref": "support-bundle-ref://openyggdrasil/bundle/1",
            "menu_items": [
                {
                    "item_ref": "receipt-ref://openyggdrasil/receipt/1",
                    "item_kind": "production_receipt",
                    "label": "contract pressure test receipt",
                    "source_ref": "support-bundle-ref://openyggdrasil/bundle/1",
                    "reason_code": "contract_pressure_test",
                }
            ],
            "input_schema_versions": ["worker_structured_receipt.v1", "support_bundle.v1"],
        }
    )


def _subagent_persona_manifest() -> dict[str, Any]:
    return build_subagent_persona_manifest(role="postman")


def _tree_ring_snapshot() -> dict[str, Any]:
    return build_tree_ring_snapshot(
        snapshot_request={
            "snapshot_request_id": "tree-ring-request:contract-pressure-test",
            "ring_id": "ring-contract-pressure-test",
            "basis_refs": ["oy-vault://sources/contract-pressure-test.md"],
        }
    )


def _wiki_continent_page() -> dict[str, Any]:
    page = {
        "schema_version": "wiki_continent_page.v1",
        "page_ref": "oy-vault://categories/software-development/contracts/pressure-test.md",
        "internal_node_id": "N-contract-pressure-test",
        "semantic_category_path": _semantic_category_path(),
        "provider_source_events": [_provider_event()],
        "decision_timeline": [_decision_timeline_event()],
        "community_growth_events": [_community_growth_event()],
        "machine_appendix_present": True,
    }
    validate_wiki_continent_page_contract(page)
    return page


PRESSURE_TESTS: dict[str, Callable[[], dict[str, Any]]] = {
    "amundsen_category_judgment.v1.schema.json": _amundsen_category_judgment,
    "community_growth_event.v1.schema.json": _community_growth_event,
    "decision_timeline_event.v1.schema.json": _decision_timeline_event,
    "memory_ticket.v1.schema.json": _memory_ticket,
    "provenance_ring_node.v1.schema.json": _provenance_ring_node,
    "provider_skill_receipt_consumer.v1.schema.json": _provider_skill_receipt_menu,
    "provider_source_event.v1.schema.json": _provider_event,
    "retrieval_candidate.v1.schema.json": _retrieval_candidate,
    "retrieval_candidate_set.v1.schema.json": _retrieval_candidate_set,
    "semantic_category_path.v1.schema.json": _semantic_category_path,
    "skill_metadata_reader.v1.schema.json": _skill_metadata_read,
    "subagent_persona_manifest.v1.schema.json": _subagent_persona_manifest,
    "tree_ring_snapshot.v1.schema.json": _tree_ring_snapshot,
    "wiki_continent_page.v1.schema.json": _wiki_continent_page,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Pressure-test contract schemas that were formerly signboard pipes.")
    parser.add_argument("--out", help="Optional JSON output path.")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for schema_name in FORMER_SIGNBOARD_SCHEMAS:
        try:
            payload = PRESSURE_TESTS[schema_name]()
            validate_contract_payload(payload, schema_name)
            rows.append(
                {
                    "schema": schema_name,
                    "status": "pass",
                    "schema_version": payload.get("schema_version"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - this is an audit report.
            rows.append(
                {
                    "schema": schema_name,
                    "status": "fail",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    result = {
        "schema_version": "contract_pressure_test.v1",
        "status": "pass" if all(row["status"] == "pass" for row in rows) else "fail",
        "tested_count": len(rows),
        "passed_count": sum(1 for row in rows if row["status"] == "pass"),
        "failed_count": sum(1 for row in rows if row["status"] == "fail"),
        "rows": rows,
        "hard_nonclaims": [
            "sample_pressure_test_is_not_full_live_provider_ux",
            "sample_pressure_test_is_not_domain_semantic_review",
            "sample_pressure_test_only_proves_schema_file_validation_paths_are_callable",
        ],
    }
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = REPO_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
