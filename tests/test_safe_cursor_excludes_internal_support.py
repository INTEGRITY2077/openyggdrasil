from runtime.retrieval.safe_index_cursor import load_safe_index_cursor, write_safe_index_cursor
from runtime.retrieval.support_exclusion_manifest import support_exclusion_for_path


def test_safe_cursor_does_not_commit_query_or_concept_internal_paths(tmp_path) -> None:
    vault = tmp_path / "vault"
    write_safe_index_cursor(
        vault_root=vault,
        cursor_id="cursor:test",
        source="test",
        committed_paths=[
            "vault/categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
            "vault/queries/domestic-dog-ecology-boundary.md",
            "vault/concepts/N-internal.md",
            "vault/concepts/PRN-internal.md",
        ],
    )

    cursor = load_safe_index_cursor(vault)

    assert cursor["committed_paths"] == [
        "vault/categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md"
    ]
    assert support_exclusion_for_path(vault_root=vault, path_value="vault/queries/example.md")[
        "excluded"
    ]
    assert support_exclusion_for_path(vault_root=vault, path_value="vault/concepts/N-example.md")[
        "excluded"
    ]
