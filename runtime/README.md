# Runtime

`runtime/` contains provider-neutral OpenYggdrasil implementation modules.

The runtime is split by role so that no single module can capture a provider
signal, promote canonical memory, query stale material, and deliver support to a
provider session without passing typed boundaries.

## Packages

| Package | Role |
| --- | --- |
| `attachments/` | Provider cold-start, attachment validation/repair, provider packaging baselines, and session-bound inbox scaffolding. |
| `capture/` | Provider runtime integrity checks and Decision Distiller normalization. |
| `admission/` | Admission and Amundsen/Nursery handoff boundaries. |
| `evaluation/` | Candidate worthiness, promotion readiness, chain health, and evaluator handoffs. |
| `cultivation/` | Seedkeeper/Nursery/Gardener helpers, lifecycle requests, conflict quarantine, and effort-aware worthiness. |
| `placement/` | Topic, episode, community, and Map Maker placement helpers. |
| `provenance/` | Provenance records and temporal semantic edge helpers. |
| `retrieval/` | Pathfinder, Graphify snapshot support, graph freshness guards, and source shortcut retrieval. |
| `delivery/` | Postman, mailbox, support bundle, packet scoring, and contamination guards. |
| `reasoning/` | Optional Reasoning Lease contracts, provider reasoning gates, effort plans, sandbox/resource boundaries, and typed unavailable results. |
| `runner/` | Thin orchestration and regression/proof entrypoints across role boundaries. |
| `common/` | Small shared utilities such as identity, JSONL, and WSL runner helpers. |

## Compatibility Policy

Some top-level `runtime/*.py` modules remain as compatibility shims or proof
entrypoints while package imports stabilize. Canonical package locations are
tracked by `runtime/shim_policy.py`, and `runtime/import_smoke.py` verifies that
both current and compatibility surfaces remain importable.

## Verification

```powershell
py -3 runtime/import_smoke.py
```
