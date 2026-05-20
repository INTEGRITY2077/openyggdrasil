from __future__ import annotations

from runtime.delivery.postman_heartbeat_cpr import build_postman_heartbeat_cpr_payload


def test_boundary_fallback_support_preserves_source_lineage_and_category_taxonomy() -> None:
    payload = build_postman_heartbeat_cpr_payload(
        live_group={
            "provider": {"status": "ready", "session_name": "ygg-pro1"},
            "ms1": {"status": "ready", "session_name": "ygg-ms1"},
            "mf1": {"status": "ready", "session_name": "ygg-mf1"},
        },
        engine_status={
            "tmux": {"status": "ready"},
            "postman_helper": {"status": "ready"},
            "mailbox": {"status": "ready"},
            "receipt_registry": {"status": "ready", "receipt_id": "receipt-1"},
        },
        mf1_receipt={
            "in_reply_to": "ask-boundary",
            "receipt_id": "receipt-1",
            "bundle": {
                "schema_version": "boundary_fallback_support_bundle.v1",
                "topic_key": "domestic-dog-ecology-boundary",
                "ring_id": "ring-1",
                "community_id": "community:domestic-dog-ecology",
                "continent": "concepts",
                "node_type": "policy",
                "source_paths": [
                    "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                    "communities/domestic-dog-ecology.md",
                ],
                "support_facts": [
                    {
                        "source_path": "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                        "text": "품종 차이는 child 후보이고 보호자 개입은 welfare sibling 후보이다.",
                    }
                ],
                "node_taxonomy": {
                    "schema_version": "wiki_node_taxonomy.v1",
                    "continent": "concepts",
                    "physical_continent": "concepts",
                    "node_type": "policy",
                    "topography_level": "tree",
                    "community_role": "member",
                    "classification_source": "category",
                    "taxonomy_status": "valid",
                },
                "origin_claims": [
                    {
                        "source_ref": "hermes-session-json://dog-session",
                        "origin_locator": "hermes-session-json://dog-session#message_index=92..103",
                        "support_fact": "dog boundary",
                    }
                ],
                "recent_rings": [
                    {
                        "provider_session_id": "dog-session",
                        "message_index_range": {"start": 92, "end": 103},
                        "anchor_hash": "a" * 64,
                        "commit_watermark": "session:dog-session:message_index:103",
                    }
                ],
            },
        },
        created_at="2026-05-20T00:00:00+00:00",
    )

    metadata = payload["mf1_support_metadata"]
    taxonomy = metadata["node_taxonomy"]

    assert payload["heartbeat_cpr_status"] == "ready"
    assert metadata["source_ref"] == "hermes-session-json://dog-session"
    assert metadata["origin_locator"] == "hermes-session-json://dog-session#message_index=92..103"
    assert metadata["provider_session_id"] == "dog-session"
    assert metadata["message_index_range"] == {"start": 92, "end": 103}
    assert metadata["anchor_hash_present"] is True
    assert metadata["commit_watermark"] == "session:dog-session:message_index:103"
    assert metadata["support_facts"] == ["품종 차이는 child 후보이고 보호자 개입은 welfare sibling 후보이다."]
    assert metadata["continent"] == "biology"
    assert metadata["node_type"] == "wiki_article"
    assert taxonomy["continent"] == "biology"
    assert taxonomy["physical_continent"] == "categories"
    assert taxonomy["node_type"] == "wiki_article"
    assert taxonomy["classification_source"] == "source_path"
