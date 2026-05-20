import json

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
