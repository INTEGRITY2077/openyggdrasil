from __future__ import annotations

from runtime.retrieval.support_exclusion_manifest import support_exclusion_for_path


def test_builtin_excludes_concept_hash_nodes_without_manifest_entry(tmp_path) -> None:
    vault = tmp_path / "vault"
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "support_exclusion_manifest.json").write_text(
        '{"schema_version":"support_exclusion_manifest.v1","patterns":[],"entries":[]}',
        encoding="utf-8",
    )

    result = support_exclusion_for_path(
        vault_root=vault,
        path_value="vault/concepts/N-new-live-node.md",
    )

    assert result["excluded"] is True
    assert result["final_support_allowed"] is not True
    assert result["exclusion_state"] == "machine_mirror"


def test_builtin_excludes_prn_nodes_without_manifest_entry(tmp_path) -> None:
    vault = tmp_path / "vault"
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "support_exclusion_manifest.json").write_text(
        '{"schema_version":"support_exclusion_manifest.v1","patterns":[],"entries":[]}',
        encoding="utf-8",
    )

    result = support_exclusion_for_path(
        vault_root=vault,
        path_value="vault/concepts/PRN-new-live-node.md",
    )

    assert result["excluded"] is True
    assert result["exclusion_state"] == "machine_mirror"
