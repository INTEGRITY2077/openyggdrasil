from __future__ import annotations

import operator  # noqa: F401 - stdlib pre-import prevents runtime/operator shadowing in this repo layout.
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from attachments.provider_attachment import bootstrap_skill_provider_session
from delivery.consumer_receipt_ingress import build_typed_unavailable
from delivery.postman_heartbeat_cpr import (
    build_postman_heartbeat_cpr_payload,
    inject_postman_heartbeat_cpr_to_provider_inbox,
    read_postman_heartbeat_cpr_packets,
)


def _live_group() -> dict:
    return {
        "provider": {"status": "present", "session_name": "ygg-pro1"},
        "op1": {"status": "present", "session_name": "ygg-op1"},
        "op2": {"status": "present", "session_name": "ygg-op2"},
    }


def _engine_status() -> dict:
    return {
        "tmux": {"status": "running", "evidence_ref": "tmux-ref://openyggdrasil/ygg-live-group"},
        "watcher": {"status": "healthy", "consumer": "postman"},
        "mailbox": {"status": "healthy", "namespace": "active"},
        "receipt_registry": {"status": "ready", "receipt_id": "op2-receipt-001"},
    }


def _op2_receipt() -> dict:
    return {
        "mail_id": "mail-001",
        "delivery_id": "delivery-001",
        "receipt_id": "receipt-001",
        "op2_query_receipt_id": "op2-query-receipt-001",
        "support_bundle": {
            "schema_version": "ring_support_bundle.v1",
            "support_facts": ["Postman handed off OP2 metadata for provider current-dialogue judgment."],
            "source_paths": ["vault/concepts/N-postman-cpr.md"],
            "source_ref": "hermes-session-json://postman-cpr-proof-001",
            "community_id": "community:postman-heartbeat-cpr",
            "currentness": "current",
        },
    }


def _ring_support_bundle() -> dict:
    return {
        "schema_version": "ring_support_bundle.v1",
        "topic_key": "live-topology-proof",
        "ring_id": "ring-live-topology",
        "community_id": "community:live-topology",
        "source_ref": "hermes-session-json://worker2-live-topology",
        "origin_locator": "hermes-session-json://worker2-live-topology#message_index=2..3",
        "provider_session_id": "worker2-live-topology",
        "message_index_range": {"start": 2, "end": 3},
        "anchor_hash": "a" * 64,
        "commit_watermark": "session:worker2-live-topology:message_index:3",
        "lifecycle_state": "ACTIVE",
        "current_authority": "active",
        "source_paths": [
            "vault/queries/live-topology-proof.md",
            "vault/_meta/provenance/live-topology-proof.md",
            "vault/concepts/PRN-live-topology.md",
            "vault/communities/live-topology.md",
        ],
        "origin_claims": [
            {
                "episode_id": "episode:ring:ring-live-topology",
                "claim_id": "claim:PRN-live-topology",
                "support_fact": "Provider CPR topology completion has ring support.",
            }
        ],
        "recent_rings": [{"ring_id": "ring-live-topology"}],
        "community_edges": [{"community_id": "community:live-topology"}],
        "semantic_edges": [{"type": "PROVENANCE_RING_SUPPORTS"}],
    }


def _korean_query_expansion() -> dict:
    return {
        "schema_version": "korean_query_expansion.v1",
        "original_query": "ㅎㄱ",
        "expansion_status": "ready",
        "expansion_tokens": ["ko_cho:ㅎㄱ", "ko_qwerty:gksrmf"],
        "expansions": ["ㅎㄱ", "한글"],
        "used_as_secondary_signal": True,
        "primary_language_analyzer": "kiwipiepy_or_existing_tokenizer",
        "hard_nonclaims": {
            "not_grammar_checker": True,
            "not_kiwi_replacement": True,
            "not_semantic_quality_proof": True,
            "not_canonical_text_rewriter": True,
            "not_es_hangul_code_copied": True,
        },
    }


def test_postman_cpr_injects_operator_brief_into_provider_inbox(tmp_path: Path) -> None:
    bootstrap_skill_provider_session(
        workspace_root=tmp_path,
        provider_id="hermes",
        provider_profile="default",
        provider_session_id="session-postman-cpr-001",
        origin_kind="provider-thread",
        origin_locator={"thread_id": "session-postman-cpr-001"},
    )

    result = inject_postman_heartbeat_cpr_to_provider_inbox(
        workspace_root=tmp_path,
        provider_id="hermes",
        provider_profile="default",
        provider_session_id="session-postman-cpr-001",
        live_group=_live_group(),
        engine_status=_engine_status(),
        op2_receipt=_op2_receipt(),
        created_at="2026-05-07T00:00:00+00:00",
    )

    payload = result["payload"]
    assert result["delivery_status"] == "created"
    assert result["packet"]["packet_type"] == "operator_brief"
    assert payload["schema_version"] == "postman_heartbeat_cpr.v1"
    assert payload["heartbeat_cpr_status"] == "ready"
    assert payload["provider_inbox_handoff"]["manual_prompt_injection_required"] is False
    assert payload["provider_inbox_handoff"]["handoff_status"] == "ready_for_provider_current_dialogue"
    assert payload["mailbox_correlation"]["mail_id"] == "mail-001"
    assert payload["mailbox_correlation"]["delivery_id"] == "delivery-001"
    assert payload["mailbox_correlation"]["receipt_id"] == "receipt-001"
    assert payload["op2_support_metadata"]["source_paths"] == ["vault/concepts/N-postman-cpr.md"]
    assert payload["hard_nonclaims"]["full_ux_passed"] is False
    assert payload["hard_nonclaims"]["postman_semantic_quality_owner"] is False

    rows = read_postman_heartbeat_cpr_packets(
        workspace_root=tmp_path,
        provider_id="hermes",
        provider_profile="default",
        provider_session_id="session-postman-cpr-001",
    )
    assert len(rows) == 1
    assert rows[0]["message_id"] == result["message_id"]


def test_postman_cpr_prefers_nested_completed_ring_support_bundle() -> None:
    op2_receipt = {
        "in_reply_to": "ask-worker2-ring",
        "delivery_id": "postman-ring-delivery",
        "receipt_id": "op2-ring-receipt",
        "bundle": {
            "contract": "support_bundle.v1",
            "source_paths": ["concepts/N-live-proof.md"],
            "support_facts": [
                {
                    "node_id": "N-live-proof",
                    "subject": "opaque-token-only provider bridge",
                }
            ],
            "support_bundle": _ring_support_bundle(),
        },
    }

    payload = build_postman_heartbeat_cpr_payload(
        live_group=_live_group(),
        engine_status=_engine_status(),
        op2_receipt=op2_receipt,
        created_at="2026-05-07T00:00:00+00:00",
    )

    metadata = payload["op2_support_metadata"]
    assert payload["heartbeat_cpr_status"] == "ready"
    assert payload["provider_inbox_handoff"]["handoff_status"] == "ready_for_provider_current_dialogue"
    assert payload["mailbox_correlation"]["mail_id"] == "ask-worker2-ring"
    assert payload["mailbox_correlation"]["op2_query_receipt_id"] == "op2-ring-receipt"
    assert metadata["status"] == "available"
    assert metadata["support_schema_version"] == "ring_support_bundle.v1"
    assert metadata["topic_key"] == "live-topology-proof"
    assert metadata["ring_id"] == "ring-live-topology"
    assert metadata["community_id"] == "community:live-topology"
    assert metadata["source_ref"] == "hermes-session-json://worker2-live-topology"
    assert metadata["origin_locator"] == "hermes-session-json://worker2-live-topology#message_index=2..3"
    assert metadata["provider_session_id"] == "worker2-live-topology"
    assert metadata["message_index_range"] == {"start": 2, "end": 3}
    assert metadata["anchor_hash_present"] is True
    assert metadata["commit_watermark"] == "session:worker2-live-topology:message_index:3"
    assert metadata["currentness"] == "active"
    assert metadata["source_paths"] == [
        "vault/queries/live-topology-proof.md",
        "vault/_meta/provenance/live-topology-proof.md",
        "vault/concepts/PRN-live-topology.md",
        "vault/communities/live-topology.md",
    ]
    assert metadata["origin_claims_count"] == 1
    assert metadata["recent_rings_count"] == 1
    assert metadata["community_edges_count"] == 1
    assert metadata["semantic_edges_count"] == 1
    assert metadata["typed_unavailable"] is None
    assert payload["hard_nonclaims"]["full_ux_passed"] is False
    assert payload["hard_nonclaims"]["graphify_full_topology_passed"] is False


def test_postman_cpr_preserves_korean_query_expansion_metadata_without_overclaim() -> None:
    ring_bundle = _ring_support_bundle()
    ring_bundle["korean_query_expansion"] = _korean_query_expansion()
    op2_receipt = {
        "in_reply_to": "ask-worker2-korean",
        "delivery_id": "postman-korean-delivery",
        "receipt_id": "op2-korean-receipt",
        "bundle": {
            "contract": "support_bundle.v1",
            "support_bundle": ring_bundle,
        },
    }

    payload = build_postman_heartbeat_cpr_payload(
        live_group=_live_group(),
        engine_status=_engine_status(),
        op2_receipt=op2_receipt,
        created_at="2026-05-07T00:00:00+00:00",
    )

    metadata = payload["op2_support_metadata"]["korean_query_expansion"]
    assert payload["heartbeat_cpr_status"] == "ready"
    assert metadata["schema_version"] == "korean_query_expansion.v1"
    assert metadata["original_query"] == "ㅎㄱ"
    assert metadata["expansion_status"] == "ready"
    assert metadata["expansion_tokens"] == ["ko_cho:ㅎㄱ", "ko_qwerty:gksrmf"]
    assert metadata["expansions"] == ["ㅎㄱ", "한글"]
    assert metadata["used_as_secondary_signal"] is True
    assert metadata["primary_language_analyzer"] == "kiwipiepy_or_existing_tokenizer"
    assert metadata["hard_nonclaims"]["not_grammar_checker"] is True
    assert metadata["hard_nonclaims"]["not_kiwi_replacement"] is True
    assert metadata["hard_nonclaims"]["not_semantic_quality_proof"] is True
    assert metadata["hard_nonclaims"]["not_canonical_text_rewriter"] is True
    assert metadata["hard_nonclaims"]["not_es_hangul_code_copied"] is True
    assert "\\" not in str(metadata)
    assert "D:/" not in str(metadata)
    assert payload["hard_nonclaims"]["postman_semantic_quality_owner"] is False


def test_postman_cpr_fails_closed_with_typed_unavailable_when_health_is_missing() -> None:
    payload = build_postman_heartbeat_cpr_payload(
        live_group={"provider": {"status": "present"}},
        engine_status={"tmux": {"status": "running"}},
        op2_receipt=None,
        created_at="2026-05-07T00:00:00+00:00",
    )

    unavailable = payload["typed_unavailable"]
    assert payload["heartbeat_cpr_status"] == "typed_unavailable"
    assert payload["provider_inbox_handoff"]["handoff_status"] == "blocked_typed_unavailable"
    assert unavailable["schema_version"] == "typed_unavailable.v1"
    assert unavailable["reason_code"] == "unresolved_evidence_ref"
    missing_refs = "\n".join(row["ref"] for row in unavailable["missing_or_rejected_refs"])
    assert "live_group_op1" in missing_refs
    assert "engine_watcher" in missing_refs
    assert "op2_receipt" in missing_refs
    assert payload["hard_nonclaims"]["readme_scorecard_promotion_allowed"] is False


def test_postman_cpr_hands_off_op2_typed_unavailable_without_topology_overclaim() -> None:
    op2_receipt = _op2_receipt()
    op2_receipt["support_bundle"] = {
        "typed_unavailable": build_typed_unavailable(
            reason_code="unresolved_evidence_ref",
            blocked_stage="recall_support_bundle",
            created_at="2026-05-07T00:00:00+00:00",
            unavailable_ref="typed-unavailable-ref://openyggdrasil/postman-cpr/op2-support",
            missing_or_rejected_refs=[
                {
                    "ref": "support-bundle-ref://openyggdrasil/postman-cpr/missing-ring",
                    "reason_code": "unresolved_evidence_ref",
                    "rejection_kind": "missing",
                }
            ],
        )
    }

    payload = build_postman_heartbeat_cpr_payload(
        live_group=_live_group(),
        engine_status=_engine_status(),
        op2_receipt=op2_receipt,
        created_at="2026-05-07T00:00:00+00:00",
    )

    assert payload["heartbeat_cpr_status"] == "ready"
    assert payload["op2_support_metadata"]["status"] == "typed_unavailable"
    assert payload["op2_support_metadata"]["typed_unavailable"]["blocked_stage"] == "recall_support_bundle"
    assert payload["hard_nonclaims"]["graphify_full_topology_passed"] is False
