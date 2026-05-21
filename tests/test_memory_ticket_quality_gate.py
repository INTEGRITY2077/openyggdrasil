from runtime.operator.producer import (
    CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD,
    _build_memory_ticket_quality_assessment,
)


def _ring_node() -> dict:
    return {
        "decision_capsule": {
            "decision": "Keep the boundary reusable.",
            "context": "The provider conversation separated related topics.",
            "conclusion": "The boundary can be reused only with source-backed support.",
            "evidence": ["hermes-session-json://session-1", "oy-vault://sources/domain-source.md"],
            "reuse_condition": "Use when a later question asks for the same boundary.",
        },
        "community": {
            "community_id": "community:biology-animal-ecology",
            "related_nodes": ["oy-vault://categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md"],
        },
        "provenance_rings": [
            {
                "ring_id": "ring-test",
                "message_index_range": {"start": 1, "end": 2},
                "anchor_hash": "abc123",
            }
        ],
        "paragraph_intent_safety_belt": {
            "decomposition_guard": CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD,
        },
        "node_taxonomy": {
            "schema_version": "wiki_node_taxonomy.v1",
            "continent": "concepts",
            "physical_continent": "concepts",
            "node_type": "policy",
            "topography_level": "tree",
            "community_role": "member",
            "classification_source": "test",
            "taxonomy_status": "valid",
        },
    }


def test_memory_ticket_quality_rejects_missing_domain_evidence_and_review() -> None:
    quality = _build_memory_ticket_quality_assessment(
        payload={
            "anchor_hash": "abc123",
            "category_community_hint": "biology / animal ecology / domestic dogs",
        },
        resolved={"status": "resolved"},
        ring_node=_ring_node(),
    )

    assert quality["verdict"] == "needs_review"
    assert "domain_evidence_resolved" in quality["quality_blocker_reason_codes"]
    assert "quality_review_executed" in quality["quality_blocker_reason_codes"]
    assert quality["recallability"] == "candidate_only"


def test_memory_ticket_quality_pass_requires_domain_evidence_review_and_semantic_links() -> None:
    quality = _build_memory_ticket_quality_assessment(
        payload={
            "anchor_hash": "abc123",
            "category_community_hint": "biology / animal ecology / domestic dogs",
            "domain_evidence_enrichment": {
                "status": "resolved",
                "accepted_evidence": ["oy-vault://sources/domain-source.md"],
            },
            "quality_review_status": "executed",
            "human_evaluator_status": "executed",
            "graph_dedupe_status": "executed",
        },
        resolved={"status": "resolved"},
        ring_node=_ring_node(),
    )

    assert quality["verdict"] == "pass"
    assert quality["quality_blocker_reason_codes"] == []
    assert quality["recallability"] == "community_and_source_path_retrievable"


def test_wiki_node_taxonomy_keeps_semantic_continent_separate_from_physical_storage() -> None:
    from runtime.memory.wiki_node_taxonomy import build_node_taxonomy, validate_node_taxonomy

    taxonomy = build_node_taxonomy(
        {
            "category": "policy",
            "semantic_category_path": {
                "path": "software-development/claude-code/extension-placement/agents",
                "segments": ["software-development", "claude-code", "extension-placement", "agents"],
            },
        },
        physical_continent="categories",
        default_node_type="policy",
    )

    assert taxonomy["continent"] == "software-development"
    assert taxonomy["physical_continent"] == "categories"
    assert validate_node_taxonomy(taxonomy)["valid"] is True
