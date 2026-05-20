from __future__ import annotations

from runtime.operator.consumer import _prepare_memory_finder_bundle


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
