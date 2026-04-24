# Runtime Retrieval

This family owns Pathfinder and related retrieval/runtime traversal logic.

Graphify policy:

- Graphify output is a derived query surface, not SOT.
- Snapshot adapters must be read-only against vault/SOT files.
- Snapshot manifests must say that Graphify is not SOT and cannot be the sole answer source.
- Provider answers must verify Graphify hints against linked SOT/provenance shortcuts.
