# Runtime Retrieval

`runtime/retrieval/` owns Pathfinder and derived retrieval support.

## Responsibilities

- retrieve lifecycle-aware support material
- prefer active canonical records by default
- require explicit historical mode for `SUPERSEDED` or `STALE` records
- preserve source refs, provenance, temporal fields, archive refs, and provider
  boundaries
- build and validate Graphify snapshot manifests
- guard graph output freshness, source refs, lineage, and shrink behavior
- turn graph query results into bounded support bundles, not final answers

## Graphify Boundary

Graphify output is derived navigation material. It can help Pathfinder find
relationships, but provider answers must verify graph hints against canonical
vault/provenance records before using them as memory.
