# OpenYggdrasil

OpenYggdrasil is a provider-neutral memory and retrieval layer for AI coding
agents.

It gives tools such as Hermes, Codex, Claude Code, Cursor, and future provider
adapters a shared way to attach to project memory without copying raw sessions,
leaking private development history, or trusting stale context as if it were
current truth.

## What Problem It Solves

LLM tools are good at local reasoning, but weak at long-lived operational
memory. The common failure pattern is simple:

1. useful decisions are scattered across provider chats, markdown notes, and
   local files;
2. old decisions stay searchable after they were superseded;
3. each provider invents a different memory format;
4. raw transcripts and private development history become tempting to store in
   the public repo;
5. retrieval returns plausible context, but cannot prove source, freshness,
   lifecycle state, or provider boundary.

OpenYggdrasil treats memory as an engine, not as a text pile. It uses typed
contracts, lifecycle state, provenance, bounded support bundles, and derived
Graphify views so an AI worker can answer with inspectable evidence instead of
unbounded chat history.

## Core Idea

The repository is organized around one rule:

> Canonical memory must be explicit, typed, source-ref backed, and lifecycle
> aware. Everything else is a support surface.

That means:

- `vault/` is the canonical memory surface.
- `contracts/` defines machine-readable boundaries between modules.
- `runtime/` implements provider-neutral capture, evaluation, cultivation,
  retrieval, delivery, and runner logic.
- `common/graphify/` builds derived graph/wiki/index views over canonical
  material, but never becomes source of truth.
- `providers/` contains provider adapters and public provider-facing manifests.

## Module Map

| Path | Role | Problem it addresses |
| --- | --- | --- |
| `contracts/` | JSON schemas for inbox packets, support bundles, reasoning leases, provider descriptors, lifecycle records, Graphify manifests, and runner results. | Prevents modules and providers from exchanging vague prose as if it were a stable API. |
| `runtime/attachments/` | Provider cold-start, provider/session attachment, inbox binding, deployment hooks, and packaging baseline helpers. | Makes a provider prove how it is attached before it can claim memory support. |
| `runtime/capture/` | Decision Distiller and provider runtime integrity checks. | Converts raw provider/session signals into bounded decision candidates instead of preserving raw chat. |
| `runtime/admission/` | Admission and Amundsen-style routing boundaries. | Decides whether a captured signal is usable, ambiguous, rejected, or needs review. |
| `runtime/evaluation/` | Evaluator, promotion worthiness, chain health scorecards, and handoff gates. | Stops weak candidates from being promoted just because they are syntactically valid. |
| `runtime/cultivation/` | Seedkeeper, Nursery, Gardener, lifecycle transition requests, conflict quarantine, and effort-aware worthiness. | Preserves evidence, proposes `ACTIVE`/`SUPERSEDED`/`STALE` lifecycle movement, and avoids blind physical deletion. |
| `runtime/placement/` | Map Maker and topic/episode placement helpers. | Places accepted memory in navigable topic/community structures without owning semantic truth. |
| `runtime/provenance/` | Provider-neutral provenance and temporal semantic edge helpers. | Keeps source, provider, time, and edge evidence attached to memory and retrieval results. |
| `runtime/retrieval/` | Pathfinder, Graphify snapshot adapters, graph freshness guards, source shortcuts, and cross-provider memory consumption checks. | Retrieves only explainable, lifecycle-aware support material instead of stale global buckets. |
| `runtime/delivery/` | Postman, mailbox store/status, support bundle construction, packet scoring, and contamination guards. | Delivers bounded support into a provider session without leaking unrelated memory or raw transcripts. |
| `runtime/reasoning/` | Optional reasoning lease contracts, provider reasoning gates, effort requirements, sandbox/resource boundaries, and typed unavailable states. | Separates deterministic base flow from high-reasoning provider work and makes missing capability visible. |
| `runtime/runner/` | Thin orchestration and regression entrypoints that connect contracts across module boundaries. | Proves chain behavior with typed results instead of background daemons or hidden side effects. |
| `common/graphify/` | Shared Graphify derivation stack. | Gives AI workers a fast graph/wiki/index view while keeping Graphify non-SOT and freshness-bound. |
| `providers/hermes/` | Hermes public provider adapter, manifest boundary, and packaging baseline notes. | Connects Hermes to OpenYggdrasil without publishing provider-native private bundles. |
| `vault/` | Canonical project memory examples and public vault surface. | Stores durable memory as source-ref backed records, not as provider transcript dumps. |

## End-to-End Flow

```text
provider/session signal
  -> attachment and integrity checks
  -> capture as a typed decision surface
  -> admission and evaluation
  -> cultivation, lifecycle, and provenance review
  -> placement and retrieval indexes
  -> bounded support bundle
  -> provider/session inbox delivery
```

The flow is intentionally split. A provider adapter should not be able to write
canonical memory directly, and a retrieval helper should not be able to turn a
derived graph hint into source of truth.

## What Is Already Explicit

- Provider attachment is contract-backed through descriptors, session
  attachments, inbox bindings, and turn deltas.
- Mailbox delivery uses bounded support bundles and contamination guards.
- Pathfinder and Graphify retrieval surfaces are treated as support material,
  not as canonical truth.
- Vault lifecycle has typed `ACTIVE`, `SUPERSEDED`, and `STALE` states.
- Reasoning Lease is optional and typed. Deterministic modules must keep working
  when provider background reasoning is unavailable.
- Hermes live foreground support is not overclaimed. The public baseline records
  live foreground as typed unavailable until the proof surface exists.

## What This Repository Is Not

OpenYggdrasil is not:

- a chat application;
- a vector database wrapper;
- a raw transcript archive;
- a provider credential manager;
- a background observer daemon;
- a place to publish private development history, provider-native bundles, or
  user-sensitive operator material.

Private development plans, raw runs, and provider-native bundles belong outside
the public repository.

## Quick Verification

Run the import smoke from the repository root:

```powershell
py -3 runtime/import_smoke.py
```

That smoke checks the public runtime import surface. Deeper provider POC,
private testbed history, and raw development evidence are maintained outside the
public repo.

## Start Points

- [`SKILL.md`](./SKILL.md): provider-facing install and operating contract.
- [`contracts/README.md`](./contracts/README.md): contract families and schema
  surface.
- [`runtime/README.md`](./runtime/README.md): runtime package policy.
- [`common/README.md`](./common/README.md): shared provider-neutral support
  stacks.
- [`providers/hermes/README.md`](./providers/hermes/README.md): Hermes public
  adapter boundary.
- [`POLICY_GRAPHIFY_COMPANION.md`](./POLICY_GRAPHIFY_COMPANION.md): Graphify
  companion policy.
- [`THIRD_PARTY_LICENSES.md`](./THIRD_PARTY_LICENSES.md): third-party license
  references.

## Design Principle

OpenYggdrasil optimizes for memory trust. A useful answer should make these
things visible:

- which memory was used;
- why it was relevant;
- which stale, superseded, conflicting, or decoy memory was rejected;
- what provider capability was unavailable;
- which typed contract carried the evidence.

The goal is not to remember more. The goal is to make AI memory harder to
pollute, easier to inspect, and safer to share across providers.
