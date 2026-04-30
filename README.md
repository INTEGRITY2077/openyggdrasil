<p align="center">
  <h1 align="center">🌳 OpenYggdrasil</h1>
  <p align="center">
    <strong>A provider-neutral memory engine for AI coding agents</strong>
  </p>
  <p align="center">
    <em>Not another RAG wrapper. A persistent, lifecycle-aware knowledge layer<br/>
    that compounds across providers — inspired by
    <a href="https://github.com/karpathy/llm-wiki">Karpathy's LLM Wiki</a>.</em>
  </p>
</p>

<p align="center">
  <a href="#why-this-exists">Why</a> •
  <a href="#how-it-works">How</a> •
  <a href="#the-12-module-chain">Modules</a> •
  <a href="#reasoning-lease">Reasoning Lease</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#inspirations--acknowledgements">Inspirations</a>
</p>

---

## Why This Exists

Every AI coding tool — Hermes, Codex, Claude Code, Cursor, Gemini CLI — has its
own way of "remembering" things. The common result:

| Problem | What happens |
|---|---|
| **Scattered decisions** | Useful context is trapped in provider chats, markdown notes, local files |
| **Stale memory** | Old decisions stay searchable long after they were superseded |
| **Provider lock-in** | Each tool invents a different memory format |
| **Transcript dumps** | Raw sessions leak into repos as "memory" |
| **No provenance** | Retrieval returns plausible context but can't prove source, freshness, or lifecycle state |

**RAG doesn't fix this.** RAG re-derives knowledge from scratch on every query.
There's no accumulation, no lifecycle, no cross-provider sharing.

**Vector databases don't fix this either.** They add infrastructure dependency
(Neo4j, Pinecone, embeddings) without solving the fundamental problem: *who
decides what to remember, what to forget, and what to deliver?*

OpenYggdrasil takes a different approach.

---

## How It Works

OpenYggdrasil treats memory as a **two-sided engine** — a production side that
captures and curates knowledge, and a consumption side that retrieves and
delivers it.

```
                    ┌─────────────────────────────────────────────┐
                    │           PRODUCTION SIDE                   │
                    │                                             │
  Provider Signal ──┤  ① Signal ─→ ② Gate ─→ ③ Seedkeeper        │
  (Hermes, Codex,   │       │                      │              │
   Claude Code,     │       ▼                      ▼              │
   Cursor, ...)     │  ④ Distiller ─→ ⑤ Evaluator                │
                    │                      │                      │
                    │                      ▼                      │
                    │  ⑥ Amundsen ─→ ⑦ Nursery ─→ ⑧ Map Maker   │
                    │                                    │        │
                    │                      ⑨ Gardener ◄──┘        │
                    └──────────────────────┬──────────────────────┘
                                           │
                                    ┌──────┴──────┐
                                    │    VAULT     │
                                    │  (Canonical  │
                                    │   Memory)    │
                                    └──────┬──────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │           CONSUMPTION SIDE                  │
                    │                                             │
                    │  ⑫ Pathfinder ─→ Bounded Support Bundle    │
                    │       │                      │              │
                    │       ▼                      ▼              │
                    │  ⑩ Postman ─────────→ ⑪ Mailbox            │
                    │                          │                  │
                    │                          ▼                  │
                    │                   Provider Session          │
                    └─────────────────────────────────────────────┘
```

### Production Side — "What to remember"

The production pipeline doesn't blindly store everything. It **distills**
provider signals into typed decision candidates, **evaluates** their worthiness,
**places** them in navigable topic structures, and **prunes** stale knowledge
through lifecycle transitions.

### Consumption Side — "What to deliver"

The consumption pipeline doesn't dump the entire vault. **Pathfinder** builds
bounded support bundles — explainable, lifecycle-aware, provenance-tracked
packages — and **Postman** delivers them through typed **Mailbox** contracts.

### The Bridge — Vault as Source of Truth

The vault is the single canonical memory surface. Graphify builds derived
graph/wiki/index views over it, but **Graphify is never source of truth** — it's
a derived visibility layer.

---

## The 12-Module Chain

| # | Module | Role | Key Insight |
|---|---|---|---|
| ① | **Signal** | Captures raw provider/session events | Preserves the original signal without mutation |
| ② | **Admission Gate** | Filters noise from signal | Not everything deserves to be remembered |
| ③ | **Seedkeeper** | Stamps provenance on each candidate | Every memory must know where it came from |
| ④ | **Distiller** | Extracts structured decisions from raw signals | Decisions, not transcripts, are the unit of memory |
| ⑤ | **Evaluator** | Scores promotion worthiness | Syntactic validity ≠ worth remembering |
| ⑥ | **Amundsen** | Judges category and novelty | Is this a known topic or a new frontier? |
| ⑦ | **Nursery** | Cultivates accepted candidates | New knowledge needs incubation before promotion |
| ⑧ | **Map Maker** | Places memory in topic/community structures | Navigable structure, not flat dumps |
| ⑨ | **Gardener** | Lifecycle transitions: ACTIVE → SUPERSEDED → STALE | Knowledge must be pruned, not just accumulated |
| ⑩ | **Postman** | Routes bounded support bundles | Delivery is a contract, not a side effect |
| ⑪ | **Mailbox** | Provider session inbox | Type-safe consumption surface |
| ⑫ | **Pathfinder** | Retrieves explainable support material | Every retrieval result carries provenance and lifecycle proof |

---

## Reasoning Lease

Some tasks require more than deterministic pipeline execution — they need
extended LLM reasoning with time budgets and isolation guarantees.

OpenYggdrasil separates this as an **optional Reasoning Lease** layer:

```
┌───────────────────────────────────────────────────────────┐
│  Reasoning Lease = 3 patterns combined                    │
│                                                           │
│  ┌─────────────────┐                                     │
│  │ Time-Budgeted   │  Fixed time budget per task          │
│  │ Autonomous Loop  │  Agent works without human presence  │
│  └─────────────────┘                                     │
│           +                                               │
│  ┌─────────────────┐                                     │
│  │ Sandbox         │  Untrusted code runs in isolation     │
│  │ Isolation       │  Failure → rollback, not corruption   │
│  └─────────────────┘                                     │
│           +                                               │
│  ┌─────────────────┐                                     │
│  │ Typed Contract  │  Results flow back through contracts  │
│  │ Integration     │  Not raw stdout or untyped artifacts  │
│  └─────────────────┘                                     │
└───────────────────────────────────────────────────────────┘
```

The base pipeline keeps working when reasoning capability is unavailable —
deterministic modules never depend on optional LLM reasoning.

---

## Quick Start

### Requirements

- Python 3.10+
- No external infrastructure required (no database, no vector store, no Docker)

### Verify Installation

```bash
# Clone the repository
git clone https://github.com/INTEGRITY2077/openyggdrasil.git
cd openyggdrasil

# Run import smoke test
python runtime/import_smoke.py

# Run the full test suite
python -m pytest tests/ -q
```

### Repository Structure

```
openyggdrasil/
├── contracts/          # JSON schemas — the API between modules
├── runtime/
│   ├── admission/      # Gate, Seedkeeper, Amundsen handoff
│   ├── capture/        # Signal capture, Decision Distiller
│   ├── evaluation/     # Evaluator, promotion worthiness
│   ├── cultivation/    # Nursery, Gardener, lifecycle
│   ├── placement/      # Map Maker, topic/episode placement
│   ├── provenance/     # Source tracking, temporal edges
│   ├── retrieval/      # Pathfinder, PTC tools, Graphify adapters
│   ├── delivery/       # Postman, Mailbox, support bundles
│   ├── reasoning/      # Reasoning Lease, provider gates
│   ├── runner/         # Orchestration, regression entrypoints
│   ├── ptc/            # Programmatic Tool Calling engine
│   └── governance/     # Phase automation
├── common/graphify/    # Derived graph/wiki/index views (non-SOT)
├── providers/hermes/   # Hermes public adapter
├── vault/              # Canonical project memory
└── tests/              # 510+ tests
```

---

## Inspirations & Acknowledgements

OpenYggdrasil stands on the shoulders of two key ideas.

### Andrej Karpathy's [LLM Wiki](https://github.com/karpathy/llm-wiki)

Karpathy articulated the core insight: instead of re-deriving knowledge via RAG
on every query, have the LLM **incrementally build and maintain a persistent
wiki**. OpenYggdrasil absorbed this philosophy directly:

| LLM Wiki Concept | OpenYggdrasil Absorption |
|---|---|
| **Raw Sources** (immutable originals) | → Provider Signal (①) — originals are never mutated |
| **The Wiki** (LLM-maintained knowledge) | → Vault — canonical memory with lifecycle states |
| **The Schema** (CLAUDE.md/AGENTS.md rules) | → `contracts/` — machine-readable boundaries |
| **Ingest** operation | → Production pipeline (Signal → Gardener) |
| **Query** operation | → Consumption pipeline (Pathfinder → Mailbox) |
| **Lint** operation | → Gardener pruning + Amundsen consistency checks |
| **`index.md`** catalog | → Pathfinder's index-based retrieval |
| **`log.md`** chronological record | → Provenance store with temporal edges |

> *"The wiki keeps getting richer with every source you add. The human's job is
> to curate sources and ask good questions. The LLM's job is everything else."*
> — Karpathy

OpenYggdrasil extends this from single-user/single-LLM to
**multi-provider/multi-agent** with typed contracts, lifecycle governance, and
provider-neutral sharing.

### [Graphify](https://github.com/paul-gauthier/graphify) (v5)

Graphify provides the structural analysis layer — turning codebases and knowledge
into navigable graphs:

| Graphify Concept | OpenYggdrasil Absorption |
|---|---|
| `detect → extract → build_graph → cluster → analyze → report → export` pipeline | → `common/graphify/` derived view engine |
| NetworkX + Leiden community clustering | → Topic/community structure for Map Maker |
| Confidence labels (EXTRACTED / INFERRED / AMBIGUOUS) | → Provenance confidence in retrieval results |
| Pure Python, local, offline | → **No external infrastructure dependency** |

### What We Explicitly Did NOT Adopt

| Rejected Approach | Why |
|---|---|
| **Graphiti/Zep** (Neo4j + embeddings) | External infrastructure dependency violates our "no database, no vector store" principle |
| **Vector similarity search** | Karpathy showed `index.md` works surprisingly well at moderate scale without embeddings |
| **Raw transcript storage** | Transcripts are provider-private; only typed decisions cross the boundary |
| **Provider-coupled memory** | Memory that only works with one tool defeats the purpose |

---

## Design Principles

1. **Memory is an engine, not a text pile.** Every piece of memory has a source,
   a lifecycle state, and a typed contract.

2. **Deterministic base, optional reasoning.** The pipeline works without LLM
   reasoning. Reasoning Lease is an opt-in enhancement.

3. **Provider-neutral by default.** No provider gets special access to the vault.
   Hermes, Codex, Claude Code, and future providers share the same contracts.

4. **No external infrastructure.** Pure Python, NetworkX for graphs, filesystem
   for storage. No database, no vector store, no Docker required for the base
   pipeline.

5. **Fail-closed, not fail-open.** When evidence is missing, the system reports
   typed unavailability — it never fabricates readiness.

6. **Derived views are never source of truth.** Graphify indexes, graph views,
   and wiki pages are derived surfaces. The vault is the only canonical surface.

---

## Current State

OpenYggdrasil is in active development. The module chain architecture is
established with 37,000+ lines of runtime code and 510+ passing tests.

**What works today:**
- Full 12-module chain contract definitions
- Provider-neutral capture, evaluation, cultivation, and retrieval logic
- Pathfinder retrieval with PTC (Programmatic Tool Calling) support
- Graphify-derived snapshot views
- Hermes provider adapter (foreground)

**What's in progress:**
- Top-level facade wiring for end-to-end pipeline pass-through
- Mailbox async delegation loop
- Bubblewrap sandbox runner integration
- Safe provider-owned gateway contract

See the [SKILL.md](./SKILL.md) for the provider-facing operating contract.

---

## Contributing

Contributions are welcome. Please read the existing `contracts/` schemas before
proposing new module interfaces — the typed contract boundary is the most
important architectural decision in the project.

## License

See [LICENSE](./LICENSE) for details.
