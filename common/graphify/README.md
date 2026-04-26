# Common Graphify

`common/graphify/` is the provider-neutral Graphify derivation stack.

Graphify is part of the preferred retrieval experience because it can expose
graph, path, wiki, and index views over canonical memory. It is still a derived
support surface, not source of truth.

## Role

- read canonical material from `vault/`
- build or validate Graphify-derived snapshots
- expose query/path/explain helpers for retrieval support
- record freshness, lineage, and source-ref evidence
- fail closed with typed unavailable output when the graph layer is missing or
  stale

## Important Files

- `graphify-corpus.manifest.json`: public manifest for the current derived
  corpus surface.
- `run_graphify_pipeline.py`: wrapper for rebuilding the derived graph surface.
- `query_graphify.py`: query helper over derived graph output.
- `validate_graphify_install.py`: installation and runtime availability check.

## Boundary

- `vault/` remains canonical.
- Graphify output can suggest support-bundle hints.
- Provider answers must verify Graphify hints against linked SOT/provenance
  records before presenting them as memory.
- Graphify failure may degrade retrieval quality, but it must not block core
  attachment, capture, lifecycle, or mailbox delivery.
