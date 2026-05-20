from __future__ import annotations

from runtime.operator.consumer import _prepare_memory_finder_bundle


def test_negated_animal_domain_is_removed_from_software_query_support() -> None:
    bundle = {
        "support_facts": [
            {
                "source_path": "categories/software-development/claude-code/extension-placement/agents/example.md",
                "text": "Plugin agents are a Claude Code extension placement topic.",
            },
            {
                "source_path": "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                "text": "Domestic Dog Ecology is an animal ecology topic.",
            },
        ],
        "source_paths": [
            "categories/software-development/claude-code/extension-placement/agents/example.md",
            "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="기존 동물 생태 community가 아니라 Claude Code Plugin agents 쪽이어야 해.",
        bundle=bundle,
        status="completed",
    )

    assert status == "completed"
    assert prepared["source_paths"] == [
        "categories/software-development/claude-code/extension-placement/agents/example.md"
    ]
    assert prepared["support_facts"] == [
        {
            "source_path": "categories/software-development/claude-code/extension-placement/agents/example.md",
            "text": "Plugin agents are a Claude Code extension placement topic.",
        }
    ]
    assert prepared["negated_domain_filter"]["applied"] is True
    assert prepared["negated_domain_filter"]["removed_path_count"] == 1


def test_negated_domain_filter_does_not_remove_positive_dog_query_support() -> None:
    bundle = {
        "support_facts": [
            {
                "source_path": "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                "text": "Walking and scent exploration belong to Domestic Dog Ecology.",
            }
        ],
        "source_paths": [
            "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="강아지가 산책을 못 해서 예민해지는 건 후각 탐색 기준이 있었나?",
        bundle=bundle,
        status="completed",
    )

    assert status == "completed"
    assert prepared["source_paths"] == [
        "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md"
    ]
    assert prepared["negated_domain_filter"]["applied"] is False


def test_single_domain_dog_query_removes_unrelated_software_support() -> None:
    bundle = {
        "support_facts": [
            {
                "source_path": "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                "text": "강아지 산책 스트레스와 후각 탐색은 Domestic Dog Ecology에 붙는다.",
            },
            {
                "source_path": "categories/software-development/claude-code/extension-placement/agents/example.md",
                "text": "Claude Code agents are a software-development placement topic.",
            },
        ],
        "source_paths": [
            "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
            "categories/software-development/claude-code/extension-placement/agents/example.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="강아지 산책 스트레스랑 후각 탐색 기준을 다시 확인해줘.",
        bundle=bundle,
        status="completed",
    )

    assert status == "completed"
    assert prepared["source_paths"] == [
        "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md"
    ]
    assert prepared["target_domain_filter"]["applied"] is True
    assert prepared["target_domain_filter"]["target_domain"] == "animal"


def test_multi_domain_query_does_not_force_single_domain_filter() -> None:
    bundle = {
        "support_facts": [
            {
                "source_path": "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                "text": "Dog ecology is animal ecology.",
            },
            {
                "source_path": "categories/software-development/claude-code/extension-placement/agents/example.md",
                "text": "Claude Code agents are software-development placement.",
            },
        ],
        "source_paths": [
            "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
            "categories/software-development/claude-code/extension-placement/agents/example.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="강아지 생태 위키랑 Claude Code agent 위키를 둘 다 비교해줘.",
        bundle=bundle,
        status="completed",
    )

    assert status == "completed"
    assert prepared["source_paths"] == [
        "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
        "categories/software-development/claude-code/extension-placement/agents/example.md",
    ]
    assert prepared["target_domain_filter"]["applied"] is False


def test_everyday_memory_word_does_not_override_dog_domain_filter() -> None:
    bundle = {
        "support_facts": [
            {
                "source_path": "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
                "text": "강아지 산책 스트레스는 Domestic Dog Ecology에 붙는다.",
            },
            {
                "source_path": "categories/memory-systems/openyggdrasil/wiki-ring/provider-durable-reuse-boundary.md",
                "text": "OpenYggdrasil memory boundary is a memory-system topic.",
            },
        ],
        "source_paths": [
            "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
            "categories/memory-systems/openyggdrasil/wiki-ring/provider-durable-reuse-boundary.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="기억이 흐릿한데 강아지 산책 스트레스 얘기는 기존 community로 이어지는 거지?",
        bundle=bundle,
        status="completed",
    )

    assert status == "completed"
    assert prepared["source_paths"] == [
        "categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md"
    ]
    assert prepared["target_domain_filter"]["applied"] is True
    assert prepared["target_domain_filter"]["target_domain"] == "animal"


def test_single_domain_dog_query_keeps_domain_specific_provenance_support() -> None:
    bundle = {
        "support_facts": [
            {
                "source_path": "_meta/provenance/domestic-dog-ecology-boundary-2e9eae6298.md",
                "text": (
                    "Keep dog walking ecology, breed variation, training ethics, and urban "
                    "wildlife impact as related but separate decision axes."
                ),
            },
            {
                "source_path": "categories/software-development/claude-code/extension-placement/agents/example.md",
                "text": "Claude Code agents are a software-development placement topic.",
            },
        ],
        "source_paths": [
            "_meta/provenance/domestic-dog-ecology-boundary-2e9eae6298.md",
            "categories/software-development/claude-code/extension-placement/agents/example.md",
        ],
        "safe_index_cursor": {
            "status": "inside",
            "final_support_allowed": True,
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text=(
            "강아지 산책 얘기에서 냄새 맡기랑 산책 부족 스트레스는 같은 글에 두고, "
            "품종 차이, 보호자 훈련, 공원 야생동물 피해는 각각 어디까지 같은 묶음으로 봐야 해?"
        ),
        bundle=bundle,
        status="completed",
    )

    assert status == "completed"
    assert prepared["source_paths"] == [
        "_meta/provenance/domestic-dog-ecology-boundary-2e9eae6298.md"
    ]
    assert prepared["target_domain_filter"]["applied"] is True
    assert prepared["target_domain_filter"]["target_domain"] == "animal"
