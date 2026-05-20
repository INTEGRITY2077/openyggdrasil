import json

from runtime.capture.provider_salience_trigger import detect_provider_memory_salience
from runtime.capture.provider_current_source_bridge import build_memory_ticket_payload_from_provider_exchange
from runtime.operator.producer import _handle_memory_ticket


def test_memory_ticket_writes_production_article_without_query_or_concept_support(
    tmp_path, monkeypatch
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "dog-ecology.md").write_text(
        "\n".join(
            [
                "# Domestic Dog Ecology",
                "Dog walking, smell, routine, and stress belong to domestic dog ecology.",
                "Breed variation is a child topic unless the breed itself becomes the question.",
                "Training ethics belongs to companion animal welfare.",
                "Urban wildlife impact belongs to urban animal ecology.",
            ]
        ),
        encoding="utf-8",
    )
    (source_root / "dog-welfare.md").write_text(
        "\n".join(
            [
                "# Companion Animal Welfare",
                "Guardian intervention, punishment, training ethics, and stress care are welfare questions.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON",
        json.dumps({"test-sources": str(source_root)}),
    )

    sessions_dir = tmp_path / "sessions"
    vault = tmp_path / "vault"
    category_anchor = vault / "categories" / "biology" / "animal-ecology" / "domestic-dogs.md"
    category_anchor.parent.mkdir(parents=True)
    category_anchor.write_text(
        "# Domestic Dogs\n\nDogs in human environments are part of animal ecology.",
        encoding="utf-8",
    )
    mailbox = tmp_path / "mailbox"
    user_text = (
        "I keep mixing dog walking smell work, walking shortage stress, breed differences, "
        "guardian training, and urban park wildlife harm. I need a stable criterion I can use later."
    )
    assistant_text = (
        "Dog walking smell work and walking shortage stress belong in Domestic Dog Ecology. "
        "Breed differences are a child topic, guardian training belongs in Companion Animal Welfare, "
        "and urban park wildlife harm belongs in Urban Animal Ecology."
    )
    payload = build_memory_ticket_payload_from_provider_exchange(
        provider_id="hermes",
        provider_profile="test",
        provider_session_id="unit-session",
        user_text=user_text,
        assistant_text=assistant_text,
        sessions_dir=sessions_dir,
    )

    result = _handle_memory_ticket(
        mailbox=mailbox,
        vault=vault,
        msg={"payload": payload, "provider_id": "hermes"},
    )

    assert result["status"] == "acknowledged"
    assert result["canonical_topic_path"].startswith("categories/")
    assert not result["canonical_topic_path"].startswith("queries/")

    seed = result["support_bundle_seed"]
    assert seed["readable_wiki_page_ref"].startswith("oy-vault://categories/")
    assert seed["community_id"] != "community:openyggdrasil-memory"
    assert all("/queries/" not in path and "://queries/" not in path for path in seed["source_paths"])
    assert all("/concepts/" not in path and "://concepts/" not in path for path in seed["source_paths"])

    assert not (vault / "queries").exists()
    assert not (vault / "concepts").exists()

    committed = seed["safe_index_cursor_sync"]["committed_paths"]
    assert all("vault/queries/" not in path for path in committed)
    assert all("vault/concepts/" not in path for path in committed)


def test_claude_code_agent_prompt_definition_does_not_route_to_memory_roles(
    tmp_path, monkeypatch
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "sub-agents.md").write_text(
        "\n".join(
            [
                "# Subagents",
                "Subagents are separate workers with their own context, tools, permissions, and model.",
                "They are an execution and delegation model inside a Claude Code session.",
            ]
        ),
        encoding="utf-8",
    )
    (source_root / "agent-teams.md").write_text(
        "\n".join(
            [
                "# Agent Teams",
                "Agent teams coordinate multiple Claude Code sessions or instances.",
                "They describe collaboration topology, not where a custom agent definition is stored.",
            ]
        ),
        encoding="utf-8",
    )
    (source_root / "plugins.md").write_text(
        "\n".join(
            [
                "# Plugins",
                "Plugins can package and distribute custom agent or subagent definitions.",
                "Plugin agents describe definition supply and distribution, not a separate execution model.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON",
        json.dumps({"claude-code": str(source_root)}),
    )

    vault = tmp_path / "vault"
    category_anchor = (
        vault
        / "categories"
        / "software-development"
        / "claude-code"
        / "extension-placement"
        / "agents.md"
    )
    category_anchor.parent.mkdir(parents=True)
    category_anchor.write_text(
        "# Claude Code Agents\n\nAgent execution and definition supply are adjacent but separate axes.",
        encoding="utf-8",
    )
    user_text = (
        "Claude Code 문서 보다가 agents 쪽이 다시 헷갈려. main agent, subagent, "
        "agent team은 실행 방식 쪽이고, 파일에 둔 agent 정의나 설정에서 고르는 "
        "agent는 정의를 어디서 공급하느냐 쪽이라고 보면 돼? 팀 문서에서 나중에 "
        "봐도 안 섞이게 어디서 끊는지만 기준으로 잡아줘."
    )
    assistant_text = (
        "main agent, subagent, agent team은 어떻게 실행되는가를 설명하는 실행 방식이고, "
        "파일, 설정, plugin으로 제공되는 agent 항목은 agent 정의가 어디서 공급되는가를 "
        "설명하는 정의 공급 경로다. plugin agents는 실제 실행 시 main agent나 subagent가 "
        "될 수 있지만 정의 공급 경로 자체를 별도의 실행 방식처럼 분류하지 않는다."
    )

    salience = detect_provider_memory_salience(f"{user_text}\n{assistant_text}")
    assert salience["trigger_kind"] != "boundary_correction"

    payload = build_memory_ticket_payload_from_provider_exchange(
        provider_id="hermes",
        provider_profile="test",
        provider_session_id="claude-code-agent-placement-unit",
        user_text=user_text,
        assistant_text=assistant_text,
        sessions_dir=tmp_path / "sessions",
    )

    result = _handle_memory_ticket(
        mailbox=tmp_path / "mailbox",
        vault=vault,
        msg={"payload": payload, "provider_id": "hermes"},
    )

    assert result["status"] == "acknowledged"
    seed = result["support_bundle_seed"]
    assert seed["semantic_category_path"]["path"] == "software-development/claude-code/extension-placement/agents"
    assert seed["community_id"] == "community:software-development-claude-code-extension-placement-agents"
    assert seed["quality_assessment"]["verdict"] == "pass"
    assert not any("memory-roles" in str(path) for path in seed["source_paths"])
