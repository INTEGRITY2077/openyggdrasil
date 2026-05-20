from runtime.cultivation.wiki_vault_janitor import _source_refs_from_related_nodes


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
