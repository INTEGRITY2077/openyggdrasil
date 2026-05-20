import json

from runtime.capture.provider_current_source_bridge import (
    _should_request_domain_evidence,
    build_memory_ticket_payload_from_provider_exchange,
)
from runtime.memory.domain_evidence import enrich_memory_ticket_payload


def test_domain_evidence_requested_for_non_meta_semantic_buckets() -> None:
    assert _should_request_domain_evidence(["animal-ecology"]) is True
    assert _should_request_domain_evidence(["animal-welfare", "urban-ecology"]) is True
    assert _should_request_domain_evidence(["agent-taxonomy", "extension-placement"]) is True


def test_domain_evidence_not_requested_for_memory_control_buckets_only() -> None:
    assert _should_request_domain_evidence(["durable-reuse"]) is False
    assert _should_request_domain_evidence(["role-boundary", "source-evidence"]) is False


def test_animal_ecology_provider_exchange_gets_domain_evidence(tmp_path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "domestic-dog-ecology.md").write_text(
        "\n".join(
            [
                "# Domestic Dog Ecology",
                "Dog walking, smell, routine, stress, breed variation, welfare, and urban park ecology must be separated by decision axis.",
                "Urban wildlife and leash disturbance belong to a nearby but separate urban ecology page.",
            ]
        ),
        encoding="utf-8",
    )
    (source_root / "companion-animal-welfare.md").write_text(
        "\n".join(
            [
                "# Companion Animal Welfare",
                "Training ethics, punishment, guardian intervention, and stress relief belong to welfare when the question is about intervention.",
            ]
        ),
        encoding="utf-8",
    )

    user_text = (
        "산책 스트레스는 개의 내부 상태를 설명하는 글이고, 품종 차이는 그 안의 변형, "
        "보호자 개입은 복지나 훈련 윤리, 도시 공원이나 야생동물 피해는 도시 동물 생태로 "
        "빼는 게 맞지? 나중에 다시 헷갈리지 않게 기준만 잡아줘."
    )
    assistant_text = (
        "산책 스트레스와 후각은 Domestic Dog Ecology, 품종 차이는 child page 후보, "
        "보호자 개입은 Companion Animal Welfare, 도시 공원과 야생동물 피해는 "
        "Urban Animal Ecology로 분리합니다."
    )
    payload = build_memory_ticket_payload_from_provider_exchange(
        provider_id="hermes",
        provider_profile="test",
        provider_session_id="unit-session",
        user_text=user_text,
        assistant_text=assistant_text,
        sessions_dir=tmp_path / "sessions",
    )

    assert payload.get("schema_version") == "memory_ticket.v1"
    assert isinstance(payload.get("domain_evidence_request"), dict)

    roots = json.dumps({"test-sources": str(source_root)})
    enriched = enrich_memory_ticket_payload(
        payload,
        vault=tmp_path / "vault",
        env={"OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON": roots},
    )

    evidence = enriched["domain_evidence_enrichment"]
    assert evidence["status"] == "resolved"
    assert len(evidence["accepted_evidence"]) >= 2
    assert enriched["quality_review_status"] == "executed"
    assert enriched["graph_dedupe_status"] == "executed"
