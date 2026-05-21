from runtime.cultivation.wiki_vault_janitor import (
    _scan_community_source_ref_drift,
    _source_refs_from_related_nodes,
    run_wiki_vault_janitor,
)


def test_janitor_resolves_source_ref_from_category_article_internal_node_id(tmp_path) -> None:
    vault = tmp_path / "vault"
    page = vault / "categories" / "biology" / "animal-ecology" / "domestic-dogs" / "dog-boundary.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "\n".join(
            [
                "# Dog Boundary",
                "## Machine Appendix",
                "```json",
                '{ "internal_node_id": "N-live-node", "source_ref": "hermes-session-json://session-1" }',
                "```",
            ]
        ),
        encoding="utf-8",
    )

    refs = _source_refs_from_related_nodes(vault, ["N-live-node"])

    assert refs == ["hermes-session-json://session-1"]


def test_janitor_resolves_source_ref_from_provenance_claim_id_when_concept_mirror_is_absent(tmp_path) -> None:
    vault = tmp_path / "vault"
    provenance = vault / "_meta" / "provenance" / "dog-boundary.md"
    provenance.parent.mkdir(parents=True)
    provenance.write_text(
        "\n".join(
            [
                "# Dog Boundary Provenance",
                '```json',
                '{ "claim_id": "claim:N-live-node", "source_ref": "hermes-session-json://session-2" }',
                '```',
            ]
        ),
        encoding="utf-8",
    )

    refs = _source_refs_from_related_nodes(vault, ["N-live-node"])

    assert refs == ["hermes-session-json://session-2"]


def test_janitor_rerenders_community_source_refs_from_related_node_provenance(tmp_path) -> None:
    vault = tmp_path / "vault"
    community = vault / "communities" / "dog-ecology.md"
    community.parent.mkdir(parents=True)
    community.write_text(
        "\n".join(
            [
                "# dog-ecology",
                "- community_id: community:dog-ecology",
                "- growth_event_count: 2",
                "- related_nodes: N-live-node",
                "- source_refs: hermes-session-json://session-2, hermes-session-json://stale#message_index=1..2",
                "",
                "```json",
                '{"schema_version":"community_growth_history.v1","growth_events":[]}',
                "```",
            ]
        ),
        encoding="utf-8",
    )
    provenance = vault / "_meta" / "provenance" / "dog-boundary.md"
    provenance.parent.mkdir(parents=True)
    provenance.write_text(
        "\n".join(
            [
                "# Dog Boundary Provenance",
                "```json",
                (
                    '{ "claim_id": "claim:N-live-node", "ring_id": "ring-1", '
                    '"source_ref": "hermes-session-json://session-2" }'
                ),
                "```",
            ]
        ),
        encoding="utf-8",
    )
    cursor = vault / "_meta" / "safe_index_cursor.json"
    cursor.write_text(
        '{"schema_version":"safe_index_cursor.v1","cursor_id":"cursor:test","committed_paths":[]}',
        encoding="utf-8",
    )

    assert _scan_community_source_ref_drift(vault)

    result = run_wiki_vault_janitor(
        vault_root=vault,
        run_id="test-community-rerender",
        source="unit-test",
        repair_community_source_ref_drift=True,
    )

    assert result["maintenance_receipt"]["status"] == "pass"
    assert result["maintenance_receipt"]["community_source_ref_drift_candidates"] == []
    repaired = community.read_text(encoding="utf-8")
    assert "- growth_event_count: 1" in repaired
    assert "- source_refs: hermes-session-json://session-2" in repaired
    assert "hermes-session-json://stale" not in repaired
    assert '"ring_id": "ring-1"' in repaired


def test_janitor_queues_duplicate_active_category_articles(tmp_path) -> None:
    vault = tmp_path / "vault"
    first = vault / "categories" / "software-development" / "claude-code" / "agents" / "agent-boundary-a.md"
    second = vault / "categories" / "software-development" / "claude-code" / "agents" / "agent-boundary-b.md"
    first.parent.mkdir(parents=True)
    for path in (first, second):
        path.write_text(
            "\n".join(
                [
                    "---",
                    "schema_version: wiki_article.v1",
                    "article_role: representative_tree",
                    "status: ACTIVE",
                    "title: Claude Code agent and extension placement boundary",
                    "---",
                    "# Claude Code agent and extension placement boundary",
                    "",
                    "## What This Page Decides",
                    "Agent runtime and definition location must remain separate.",
                    "",
                    "## Machine Appendix",
                    "{}",
                ]
            ),
            encoding="utf-8",
        )
    (vault / "_meta").mkdir(exist_ok=True)
    (vault / "_meta" / "safe_index_cursor.json").write_text(
        '{"schema_version":"safe_index_cursor.v1","status":"configured","cursor_id":"cursor:test","committed_paths":[]}',
        encoding="utf-8",
    )

    result = run_wiki_vault_janitor(
        vault_root=vault,
        run_id="test-duplicate-category-articles",
        source="unit-test",
        write=False,
    )

    decisions = result["maintenance_receipt"]["duplicate_repair_decisions"]
    assert result["maintenance_receipt"]["status"] == "partial"
    assert any(
        decision["suggested_action"] == "review_category_article_duplicate_or_tombstone_superseded_page"
        and decision["repair_queue_status"] == "queued"
        for decision in decisions
    )


def test_janitor_ignores_support_excluded_category_duplicate(tmp_path) -> None:
    vault = tmp_path / "vault"
    first = vault / "categories" / "software-development" / "claude-code" / "agents" / "agent-boundary-a.md"
    second = vault / "categories" / "software-development" / "claude-code" / "agents" / "agent-boundary-b.md"
    first.parent.mkdir(parents=True)
    for path in (first, second):
        path.write_text(
            "\n".join(
                [
                    "---",
                    "schema_version: wiki_article.v1",
                    "article_role: representative_tree",
                    "status: ACTIVE",
                    "title: Claude Code agent and extension placement boundary",
                    "---",
                    "# Claude Code agent and extension placement boundary",
                ]
            ),
            encoding="utf-8",
        )
    (vault / "_meta").mkdir(exist_ok=True)
    (vault / "_meta" / "safe_index_cursor.json").write_text(
        '{"schema_version":"safe_index_cursor.v1","status":"configured","cursor_id":"cursor:test","committed_paths":[]}',
        encoding="utf-8",
    )
    (vault / "_meta" / "support_exclusion_manifest.json").write_text(
        """
{
  "schema_version": "support_exclusion_manifest.v1",
  "entries": [
    {
      "path": "vault/categories/software-development/claude-code/agents/agent-boundary-b.md",
      "exclusion_state": "superseded_duplicate_article",
      "final_support_allowed": false,
      "reason_codes": ["superseded_by_canonical_article"]
    }
  ],
  "patterns": []
}
""",
        encoding="utf-8",
    )

    result = run_wiki_vault_janitor(
        vault_root=vault,
        run_id="test-excluded-duplicate-category-articles",
        source="unit-test",
        write=False,
    )

    assert result["maintenance_receipt"]["duplicate_title_candidates"] == []
    assert not any(
        decision["suggested_action"] == "review_category_article_duplicate_or_tombstone_superseded_page"
        for decision in result["maintenance_receipt"]["duplicate_repair_decisions"]
    )
