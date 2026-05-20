from __future__ import annotations

import json

from runtime.operator.consumer import (
    _prepare_memory_finder_bundle,
    _prepare_memory_finder_bundle_with_fallback,
)


def test_korean_boundary_query_aligns_with_english_article_support() -> None:
    bundle = {
        "support_facts": [
            (
                "Keep dog walking ecology, breed variation, training ethics, and urban wildlife impact "
                "as related but separate decision axes unless a later source explicitly bridges them."
            )
        ],
        "source_paths": [
            "categories/biology/animal-ecology/domestic-dogs.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="산책 스트레스 기준에서 품종 차이와 사람의 개입은 같은 문서에 둬도 되는지 저장된 위키 근거로 찾아줘.",
        bundle=bundle,
        status="completed",
    )

    assert status == "completed"
    assert prepared["support_facts"] == bundle["support_facts"]
    assert prepared["source_paths"] == bundle["source_paths"]
    assert prepared["worker_query_alignment"]["status"] in {"aligned", "aligned_with_limits"}
    assert "breed" in prepared["worker_query_alignment"]["boundary_alignment"]["covered_terms"]
    assert "training" in prepared["worker_query_alignment"]["boundary_alignment"]["covered_terms"]


def test_korean_boundary_query_still_rejects_unrelated_english_support() -> None:
    bundle = {
        "support_facts": [
            "Claude Code plugin agents are a software extension placement topic.",
        ],
        "source_paths": [
            "categories/software-development/claude-code/extension-placement/agents.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="산책 스트레스 기준에서 품종 차이와 사람의 개입은 같은 문서에 둬도 되는지 저장된 위키 근거로 찾아줘.",
        bundle=bundle,
        status="completed",
    )

    assert status != "completed"
    assert prepared["support_facts"] == []
    assert prepared["typed_unavailable"]["reason_code"].startswith("typed_unavailable_")


def test_korean_boundary_fallback_uses_semantic_article_aliases(tmp_path) -> None:
    vault = tmp_path / "vault"
    domestic = vault / "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md"
    welfare = vault / "categories/biology/animal-welfare/companion-animal-welfare.md"
    urban = vault / "categories/biology/animal-ecology/urban-animal-ecology.md"
    domestic.parent.mkdir(parents=True, exist_ok=True)
    welfare.parent.mkdir(parents=True, exist_ok=True)
    urban.parent.mkdir(parents=True, exist_ok=True)
    domestic.write_text(
        "# Domestic Dog Ecology\n\n"
        "Keep dog walking ecology, scent exploration, missed walk stress, and breed variation "
        "as related but separate decision axes.\n",
        encoding="utf-8",
    )
    welfare.write_text(
        "# Companion Animal Welfare\n\n"
        "Training ethics, human intervention, owner responsibility, welfare, reward and punishment "
        "belong to the companion animal welfare sibling page.\n",
        encoding="utf-8",
    )
    urban.write_text(
        "# Urban Animal Ecology\n\n"
        "Urban wildlife impact, park conflict, disease transmission, and free-roaming dogs "
        "belong to the urban animal ecology split page.\n",
        encoding="utf-8",
    )
    cursor = vault / "_meta/safe_index_cursor.json"
    cursor.parent.mkdir(parents=True)
    cursor.write_text(
        json.dumps(
            {
                "schema_version": "safe_index_cursor.v1",
                "cursor_id": "cursor-test",
                "committed_paths": [
                    "vault/categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                    "vault/categories/biology/animal-welfare/companion-animal-welfare.md",
                    "vault/categories/biology/animal-ecology/urban-animal-ecology.md",
                ],
            }
        ),
        encoding="utf-8",
    )

    prepared, status = _prepare_memory_finder_bundle_with_fallback(
        query_text=(
            "냄새 맡기랑 산책 부족 스트레스는 개 생태 글 중심이고, 품종 차이는 하위 변형, "
            "보호자 훈련은 복지 쪽, 야생동물 피해는 도시 생태 쪽으로 갈라진다는 선이 맞는지 확인해줘."
        ),
        bundle={
            "support_facts": ["Claude Code plugin agents are a software extension placement topic."],
            "source_paths": [
                "categories/software-development/claude-code/extension-placement/agents/example.md"
            ],
            "safe_index_cursor": {
                "schema_version": "safe_index_cursor_check.v1",
                "status": "inside",
                "final_support_allowed": True,
            },
        },
        status="completed",
        vault=vault,
    )

    assert status == "completed"
    assert prepared["safe_index_cursor"]["status"] == "inside"
    assert "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md" in prepared["source_paths"]
    assert "categories/biology/animal-welfare/companion-animal-welfare.md" in prepared["source_paths"]
    assert "categories/biology/animal-ecology/urban-animal-ecology.md" in prepared["source_paths"]
    covered = set(prepared["worker_query_alignment"]["boundary_alignment"]["covered_terms"])
    assert {"dog", "ecology", "training", "welfare", "urban", "wildlife"} <= covered
