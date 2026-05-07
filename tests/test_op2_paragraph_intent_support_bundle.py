import operator  # noqa: F401 - stdlib pre-import prevents runtime/operator shadowing in this repo layout.
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from runtime.retrieval.pathfinder_tools import build_ring_support_bundle
from runtime.operator.consumer import run_consumer


VAULT = Path(__file__).resolve().parent / "fixtures" / "op2_support_bundle_vault"
SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "typed_unavailable.v1.schema.json"


def test_prn_support_bundle_exposes_paragraph_intent_source_community_and_currentness():
    bundle = build_ring_support_bundle(
        query_text="PRN-e9e232e3e9e65c05 Provider autonomous salience trigger paragraph intent safety belt source lineage",
        vault_root=VAULT,
    )

    assert bundle["schema_version"] == "ring_support_bundle.v1"
    assert bundle["topic_id"] == "PRN-e9e232e3e9e65c05"
    assert bundle["ring_id"] == "ring-99453dc626bb5045"
    assert bundle["community_id"] == "community:openyggdrasil-provider-behavior-contract-memory-authoring-bridge"
    assert bundle["source_ref"] == "hermes-session-json://oy-live-hook-proof-1778026500"
    assert bundle["origin_locator"] == "hermes-session-json://oy-live-hook-proof-1778026500#message_index=0..1"
    assert bundle["provider_session_id"] == "oy-live-hook-proof-1778026500"
    assert bundle["message_index_range"] == {"start": 0, "end": 1}
    assert bundle["anchor_hash"] == "27fbbb875f07345c48df8bba87ca3354a305dcc8d49fc287cb29567f8944d5f4"
    assert bundle["commit_watermark"] == "session:oy-live-hook-proof-1778026500:message_index:1"
    assert bundle["lifecycle_state"] == "ACTIVE"
    assert bundle["current_authority"] == "active"

    safety_belt = bundle["paragraph_intent_safety_belt"]
    assert safety_belt["intent_field"].startswith("Provider 기억 보존은 사용자 explicit 명령")
    assert safety_belt["decomposition_guard"] == "preserve_paragraph_intent_before_decision_atoms"
    assert safety_belt["min_split_unit"] == "paragraph_intent"
    assert safety_belt["category_community_hint"] == "OpenYggdrasil provider behavior contract / memory authoring bridge"
    assert bundle.get("typed_unavailable") is None

    source_paths = "\n".join(bundle["source_paths"])
    assert "vault/queries/provider는-사용자-저장-명령" in source_paths
    assert "vault/_meta/provenance/provider는-사용자-저장-명령" in source_paths
    assert "vault/concepts/PRN-e9e232e3e9e65c05.md" in source_paths
    assert "vault/communities/openyggdrasil-provider-behavior-contract-memory-authoring-bridge.md" in source_paths


def test_ring_support_bundle_fails_closed_with_typed_unavailable_shape():
    bundle = build_ring_support_bundle(
        query_text="zzzz_unresolved_anchor_20260506_no_shared_tokens",
        vault_root=VAULT,
    )

    unavailable = bundle["typed_unavailable"]
    schema = Draft202012Validator.META_SCHEMA  # force import-time availability check
    assert schema
    contract = __import__("json").loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(contract).validate(unavailable)
    assert unavailable["reason_code"] == "unresolved_evidence_ref"
    assert unavailable["blocked_stage"] == "recall_support_bundle"
    assert unavailable["fabricated_answer"] is False
    assert unavailable["raw_provider_material_included"] is False


def _write_live_topology_fixture(vault: Path) -> None:
    query = vault / "queries" / "live-topology-proof.md"
    provenance = vault / "_meta" / "provenance" / "live-topology-proof.md"
    prn_concept = vault / "concepts" / "PRN-live-topology.md"
    legacy_concept = vault / "concepts" / "N-live-proof.md"
    community = vault / "communities" / "live-topology.md"
    for path in (query, provenance, prn_concept, legacy_concept, community):
        path.parent.mkdir(parents=True, exist_ok=True)

    ring = {
        "ring_id": "ring-live-topology",
        "source_ref": "hermes-session-json://worker2-live-topology",
        "origin_locator": "hermes-session-json://worker2-live-topology#message_index=2..3",
        "provider_session_id": "worker2-live-topology",
        "message_index_range": {"start": 2, "end": 3},
        "anchor_hash": "a" * 64,
        "commit_watermark": "session:worker2-live-topology:message_index:3",
    }
    paragraph = {
        "intent_field": "Preserve Provider current-dialogue CPR reflection as a topology proof.",
        "decomposition_guard": "preserve_paragraph_intent_before_decision_atoms",
        "min_split_unit": "paragraph_intent",
        "why_not_atomic": "The route proof needs ring, community, source path, and currentness together.",
        "topic_hint": "Provider CPR topology",
        "category_community_hint": "OpenYggdrasil provider CPR topology completion",
    }
    community_payload = {
        "community_id": "community:live-topology",
        "placement_reason": "Provider CPR topology completion proof",
        "related_nodes": ["PRN-live-topology"],
    }
    page = f"""---
id: PRN-live-topology
title: Provider CPR topology completion
type: workflow
status: ACTIVE
community: community:live-topology
sources: [hermes-session-json://worker2-live-topology]
root_claim: Provider CPR topology completion has ring support.
current_authority: active
ring_id: ring-live-topology
lifecycle_state: ACTIVE
---
# Provider CPR topology completion

## Provenance Rings
```json
[{json.dumps(ring)}]
```

## Community Placement
```json
{json.dumps(community_payload)}
```

## Paragraph Intent Safety Belt
```json
{json.dumps(paragraph)}
```
"""
    query.write_text(page, encoding="utf-8")
    prn_concept.write_text(page, encoding="utf-8")
    legacy_concept.write_text(
        page.replace("id: PRN-live-topology", "id: N-live-proof\ncanonical_node_id: PRN-live-topology")
        .replace("title: Provider CPR topology completion", "title: opaque-token-only provider bridge")
        + "\nopaque-token-only\n",
        encoding="utf-8",
    )
    provenance.write_text(
        "# Provenance Rings\n```json\n"
        + json.dumps(
            {
                "episode_id": "episode:ring:ring-live-topology",
                "claim_id": "claim:PRN-live-topology",
                "support_fact": "Provider CPR topology completion has ring support.",
                "ring_id": "ring-live-topology",
                "community_id": "community:live-topology",
                "derived_from": "queries/live-topology-proof.md",
                "source_ref": "hermes-session-json://worker2-live-topology",
                "origin_locator": "hermes-session-json://worker2-live-topology#message_index=2..3",
            }
        )
        + "\n```\n",
        encoding="utf-8",
    )
    community.write_text(
        "# live-topology\n\n- community_id: community:live-topology\n- ring_id: ring-live-topology\n",
        encoding="utf-8",
    )


def test_ring_support_bundle_uses_matched_node_when_query_text_cannot_select_topic(tmp_path):
    _write_live_topology_fixture(tmp_path)

    bundle = build_ring_support_bundle(
        query_text="opaque-token-only",
        vault_root=tmp_path,
        matched_nodes=[
            {
                "node_id": "N-live-proof",
                "_source_path": "vault/concepts/N-live-proof.md",
            }
        ],
    )

    assert bundle["schema_version"] == "ring_support_bundle.v1"
    assert bundle["topic_key"] == "live-topology-proof"
    assert bundle["ring_id"] == "ring-live-topology"
    assert bundle["community_id"] == "community:live-topology"
    assert bundle.get("typed_unavailable") is None
    assert "vault/queries/live-topology-proof.md" in bundle["source_paths"]
    assert "vault/_meta/provenance/live-topology-proof.md" in bundle["source_paths"]
    assert "vault/concepts/PRN-live-topology.md" in bundle["source_paths"]
    assert "vault/communities/live-topology.md" in bundle["source_paths"]


def test_consumer_attaches_completed_ring_bundle_from_matched_node(tmp_path):
    _write_live_topology_fixture(tmp_path)
    mailbox = tmp_path / "mailbox"
    mailbox.mkdir()
    (mailbox / "queries.jsonl").write_text(
        json.dumps({"mail_id": "ask-live", "payload": {"query_text": "opaque-token-only"}}) + "\n",
        encoding="utf-8",
    )

    run_consumer(mailbox, tmp_path)

    receipt = json.loads((mailbox / "query_receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    ring_bundle = receipt["bundle"]["support_bundle"]
    assert ring_bundle["ring_id"] == "ring-live-topology"
    assert ring_bundle["community_id"] == "community:live-topology"
    assert ring_bundle.get("typed_unavailable") is None
    assert receipt["bundle"]["source_paths"] == ["concepts/N-live-proof.md"]
