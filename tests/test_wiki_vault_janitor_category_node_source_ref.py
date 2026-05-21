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
