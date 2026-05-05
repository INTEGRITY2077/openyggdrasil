<p align="center">
  <h1 align="center">🌳 openyggdrasil</h1>
  <p align="center">
    <strong>A provider-neutral memory engine for AI coding agents</strong>
  </p>
  <p align="center">
    <em>A persistent, lifecycle-aware knowledge layer<br/>
    that compounds across providers — inspired by
    <a href="https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f">Karpathy's LLM Wiki</a>.</em>
  </p>
  <p align="center">
    English · <a href="./README.ko.md">한국어</a>
  </p>
</p>

<p align="center">
  <a href="#why-this-exists">Why</a> •
  <a href="#how-it-works">How</a> •
  <a href="#the-12-module-chain">Modules</a> •
  <a href="#reasoning-lease">Reasoning Lease</a> •
  <a href="#system-requirements--setup">Setup</a> •
  <a href="#inspirations--acknowledgements">Inspirations</a>
</p>

> ⚠️ **15th Production UX Realignment**
>
> openyggdrasil is a runtime aimed at extending Karpathy-style LLM Wiki into
> provider-neutral production memory. This document is **not** a production-ready
> completion claim. As of 2026-05-06, the project is realigning the boundaries
> around SourceRef, PTC Kitchen, Provenance Ring, Graphify, TMUX witness,
> Session Attach, and Operator Talk.
>
> Current state: provider-neutral production memory direction is ACTIVE ·
> production-ready is NOT CLAIMED · multi-provider same UX is NOT PASS ·
> some Hermes/OP1/OP2 POCs are partially verified.

### 📊 15th Alignment Scorecard — 80/100 (2026-05-06)

| Category | Score/State | Verdict |
|---|---:|---|
| Karpathy LLM Wiki philosophy/architecture alignment | 86-ish | Vault/Markdown/SOT, lifecycle, and Graphify-as-derived-view are directionally aligned |
| Current implementation completeness | 74-ish | Hermes-centered POCs and some runtime surfaces exist, but provider-neutral boundaries are not closed |
| Overall alignment | **80/100** | The direction is sound, but P0/P1/P2/P3 gates remain open |
| production-ready | **NOT CLAIMED** | Test count or a POC is not enough to claim production readiness |

#### Top-Level Realignment Notes

| Previous wording | 15th-aligned wording |
|---|---|
| “code complete”, “91%”, “100% LIVE modules” | Overclaims completion. Use 80/100 alignment plus gate-based verdicts instead |
| “cross-provider memory access verified” | Separate fake/POC evidence from real same-UX provider parity. Same UX is still NOT PASS |
| “PTC full-chain verified” | PTC IPC/sandbox pieces exist, but production/consumption kitchen split, typed egress, and sandbox fail-closed are NOT PASS |
| “Graphify live/full topology” | Graphify is a derived view, not SOT. Full topology support-bundle verification is PARTIAL |
| “TMUX live session” | TMUX is a human visual witness, not the core execution path |
| “`ygg attach/talk` works now” | Global attach and direct Operator Talk are required gates, but they are NOT PASS |

### Current Responsibility Boundary Status

#### Required Promotion Group — 15th Boundary Modules

These rows are not optional README commentary. They are the 15th realignment
boundary modules that must stay visible until each gate is closed.

| Area | Current Verdict | Reason |
|---|---|---|
| Vault / Markdown SOT | BOUNDED LIVE | The canonical memory surface is Vault/Markdown and takes precedence over Graphify |
| Mailbox / Receipt / Event Log | BOUNDED LIVE | Background-first machine-readable evidence; stronger than TMUX witness |
| Provider Common Boundary | P0 IN PROGRESS | Common runtime still needs Hermes default/direct import removal |
| SourceRef Resolver Registry | PARTIAL | Common registry must stop knowing provider-specific storage directly |
| Affordance Intent Router | NOT PASS | LLM-facing handles must use affordance contracts, not signature-only or provider-specific wording |
| PTC Production Kitchen | NOT PASS | write/mutate role, evidence, receipt, and schema responsibilities are not closed |
| PTC Consumption Kitchen | NOT PASS | read/search/support-only role split and Vault mutation ban are not closed |
| PTC Egress / Sandbox Gate | NOT PASS | raw stdout debug-only, typed egress, and production sandbox fail-closed remain open |
| Provenance Ring Lineage | PARTIAL | A POC vertical slice exists, but append-only accumulation and overwrite separation remain open |
| Graphify Support Verifier | PARTIAL | Graphify hints must be reverified against Vault; full topology support verification is unfinished |
| TMUX Live Witness | POLICY ONLY | Human observation surface; does not replace background execution success |
| Session Attach Gateway | NOT PASS | Global `ygg` attach/status/tmux must resolve an active project/session registry without spawning implicit memory work |
| Interactive Operator Talk Lane | NOT PASS | Direct OP1/OP2 conversation must enter through typed mailbox/event input, not raw TMUX/stdin injection |

#### Promotion Candidate Group — Acceptance / UX Gates

These are important gates, but they are not yet promoted into standalone
15th module-definition files. Until promoted, they should be treated as
acceptance criteria that constrain the required modules above.

| Candidate | Current Verdict | Promotion Trigger |
|---|---|---|
| Provider Final Answer UX | NOT PASS | Promote when provider/operator outputs need a dedicated contract that starts with judgment, not workflow trace |
| Cross-Provider Same UX | NOT PASS | Promote when Hermes POC evidence must be generalized into a provider-neutral CLI UX contract |

#### PASS Vocabulary

| Term | Meaning |
|---|---|
| `BOUNDED LIVE` | Narrow code/test/log evidence exists. It is not whole-product completion |
| `PARTIAL` | Direction and partial implementation exist, but core gates remain open |
| `NOT PASS` | The current evidence cannot support the claim |
| `POLICY ONLY` | The operating policy exists; functional proof is still separate |

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

> **The Fundamental Difference — When You Pay the Cognitive Cost:**
> - **RAG (Read-time):** Raw text → chunk → embed → Vector DB. Similarity search **at query time**. Retrieval quality is bounded by **ingestion quality**. If what you stored is unstructured, no embedding model can make the search results structured.
> - **openyggdrasil (Write-time):** Provider delegates (save intent) → Operator Session processes **at production time**: Distill → Evaluate → Classify → Plant into structured Vault. Search operates on **pre-structured knowledge**.
>
> In Karpathy's analogy: RAG greps raw source code every time. openyggdrasil runs a **pre-compiled binary**.

**Vector databases don't fix this either.** They add infrastructure dependency
(Neo4j, Pinecone, embeddings) without solving the fundamental problem: *who
decides what to remember, what to forget, and what to deliver?*

openyggdrasil takes a different approach.

### 🛡️ 3-Tier Vector Replacement Strategy
Instead of using heavy vector databases or ElasticSearch, openyggdrasil achieves 10x token efficiency through a 3-tier deterministic filtering pipeline on a pure local file system:

1. **L1 Structural Filtering (YAML Frontmatter)**: Filters out stale knowledge (`SUPERSEDED`) before retrieval, addressing a common weakness of vector similarity searches. It uses frontmatter metadata (`status`, `tags`, `type`) for deterministic pre-filtering.
2. **L2 Topological Navigation (NetworkX)**: Traces explicit causality instead of probabilistic similarity. It converts `Sources` links between documents into a NetworkX graph, and uses the Louvain community algorithm to identify topic clusters that should be considered together.
3. **L3 Programmatic Scanning (PTC Full-text)**: Reduces token waste caused by carelessly shoving 10-20 candidates into the LLM's context window. A Python script (PTC) scans files in the background and returns refined conclusions (variable names, code snippets) to the agent. The goal is to reduce **"Lost in the Middle"** failure modes and round-trip token overhead.

### Cross-Provider Pollination

openyggdrasil functions as a shared knowledge repository that is not locked into any specific tool.

- **Agent A writes:** In a session with Agent A (e.g., Cursor), you decide on an architecture and it gets recorded in the Vault. (Source: `provider_id: cursor`)
- **Agent B reads and updates:** Days later, you open Agent B (e.g., Claude Code). It searches for, reads the document Agent A wrote, and continues the work. If the decision changes, Agent B pushes the old knowledge to `SUPERSEDED` and writes the new knowledge.
- **Agent A recognizes it again:** The next time Agent A connects, it doesn't read the stale knowledge it wrote in the past, but the updated knowledge maintained by Agent B.

This is possible because all agents abandon their internal transcript formats and share the same canonical Vault specification—the **strict frontmatter schema (Markdown + YAML)** of openyggdrasil.

## Core Philosophy

openyggdrasil fuses four core philosophies to prevent "memory erosion" in a fragmented multi-agent environment.

### 1. Persistent Knowledge Base (LLM Wiki)
Inspired by Andrej Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Instead of injecting context via RAG on every query, we "let the LLM incrementally build and curate a persistent wiki (SOT)." However, a simple flat wiki makes it difficult to explore macroscopic contexts.

### 2. Domain Separation = Defining Continents (Continents & Terrain)
In openyggdrasil, a category is not just a folder, but an **independent knowledge domain (Continent)**. Strict role separation prevents context contamination.
- **Amundsen** judges whether incoming knowledge belongs to an existing domain ('known continent') or if a 'new continent' must be charted, establishing the boundaries.
- **Map Maker** plans the relative topology and reference coordinates within that domain.
- **Gardener** protects the taxonomy, ensuring knowledge isn't miscategorized, and handles the physical file I/O operations.

### 3. Provenance Tracking and Lineage (Tree Rings & Evolution)
If a system merely overwrites files with the latest data, crucial foundational contexts (Origins) are eventually lost. *"Time flows linearly, but context does not evolve linearly."* To prevent this, knowledge is managed as an evolving lineage.
- **Tree Ring Engraving:** Captured knowledge blocks are stamped with provenance (`provider_id`, `session_uid`, `timestamp`) at the data-model level when admitted.
- Foundational decisions (Roots and Trunks) are preserved, while abandoned logic (Branches) is explicitly marked as invalid (`SUPERSEDED`) rather than physically deleted. This gives agents a bounded lineage path to inspect a decision's evolution across providers.

### 4. Structural Relationship Network (Graphify Topology)
To transcend the physical limits of categorized knowledge, we apply Safi Shamsi's [Graphify (v5)](https://github.com/safishamsi/graphify) concept.
The Markdown Vault is parsed and converted into a mathematical graph and community clusters using NetworkX Louvain community detection. This allows traversal across semantic edges, connecting related knowledge even if stored in different folders.

---

> *"The wiki becomes richer with every source added. A human's job is to curate the sources and ask good questions. The LLM's job is everything else."* — Karpathy

Through this **'Construction of a Knowledge Ecosystem and Topological Fusion'**, openyggdrasil operates beyond a simple collection of texts—it acts as a **pure-local offline multi-agent memory system** that natively understands relationship networks without relying on external Vector DBs.

### The Bridge — Vault and Graphify

The system strictly isolates static file storage (Vault) from the dynamic relationship network (Graphify).

```text
┌────────────────────────────────────────┐
│  Graphify (Derived Topology / Non-SOT) │
│  [Math Nodes] ──(Edges)── [Clusters]   │  <-- Can be deleted and regenerated anytime
└─────────────────▲──────────────────────┘
                  │ (Real-time extraction & validation)
        [ skill_frontmatter_parser.py ]
                  │
┌─────────────────▼──────────────────────┐
│  Vault (Single Source of Truth / SOT)  │
│  ├── concepts/   (--- YAML ---)        │  <-- Immutable Markdown files
│  └── entities/   (--- YAML ---)        │
└────────────────────────────────────────┘
```

#### Vault: The Canonical Memory Surface

The Vault is the single source of truth (SOT). Knowledge produced by providers is ultimately recorded in the Vault, following this structure:

```
vault/
├── SCHEMA.md           # This schema file
├── index.md            # Master topic catalog (Karpathy's index.md)
├── log.md              # Chronological record (Karpathy's log.md)
├── concepts/           # Technical ideas, patterns, principles, recurring themes
├── entities/           # People, organizations, products, models, systems
├── comparisons/        # Side-by-side analysis, decision tradeoffs
├── queries/            # High-value answers with high derivation cost
├── _meta/              # Operational notes, templates, maps, governance
│   └── provenance/     # Provenance tracking records
└── raw/                # Original supporting materials (not raw transcripts)
```

**Frontmatter of each page:**

```yaml
---
title: Page Title
created: 2026-04-30
updated: 2026-04-30
type: entity | concept | comparison | query | summary
status: ACTIVE | SUPERSEDED
tags: [classification tags]
sources: [source refs or public paths]
---
```

## System Requirements & Setup

openyggdrasil is designed to operate as a session-scoped skill attached to your AI provider (e.g., Hermes, Claude Code, Cursor). The target operating model does not require system-level background daemons or separate server management. Operator Sessions should be bound to their Provider Session's lifetime and exit on timeout or completion, but this is not a production-ready guarantee yet.

> **⚠️ Reasoning Lease Model (Asynchronous Multiplexing):**
> openyggdrasil does not have its own API keys; it **borrows (leases) the reasoning tokens of the provider agent (IDE) in reverse**.
> In the target non-blocking path, the Operator runs behind the user chat and therefore needs an explicit provider-owned reasoning lease. A provider adapter may satisfy that lease through scoped auth delegation or asynchronous task-contract multiplexing, but the common boundary must remain provider-neutral. This boundary is not a production-ready claim.

### 1. How Providers Recognize openyggdrasil

Providers attach to openyggdrasil by reading the **`SKILL.md`** manifest at the repository root. To initiate the connection:
- Point your agent's skill configuration to the absolute path of `SKILL.md`.
- The agent reads this contract, which defines the declared entrypoints, command shapes, and boundaries for memory retrieval and capture.

### 2. System Requirements & Dependency Installation

openyggdrasil runs purely locally. The core runtime relies mostly on the Python Standard Library; optional Graphify-derived views and sandbox isolation require the following dependency stack:

**Supported Operating Systems:**
- **Linux / WSL2 Focus**: openyggdrasil's core Reasoning Lease Sandbox depends on `bubblewrap` for unprivileged Linux container isolation.
  - **Note (Cross-OS Execution):** While it is physically possible to call openyggdrasil inside WSL2 from a provider running natively on Windows (Cross-border Tunneling), it is **strongly discouraged**. This is due to the extreme complexity of Windows-WSL2 path translation, severe I/O performance degradation (via 9P protocol), and a high risk of deadlocks caused by Stdin/Stdout encoding differences. For stable operation, we highly recommend running the AI provider directly within the same WSL2 environment.

**Core Prerequisite:**
- **`Python 3.10+`**: Must be installed and accessible in the local environment.

**Python Packages (via pip):**
- **`graphifyy`**: (Note: The conceptual name is Graphify(v5), but the PyPI package name is `graphifyy`) The core companion package for structural analysis and graph building
- **`networkx`**: for graph derivation, node indexing, traversal, and Louvain community detection
- **`jsonschema`**: for strictly validating provider contracts and mailbox schemas
- **`pyyaml`**: for reading/writing configuration and manifest files
- **`pytest`**: for local contract verification and smoke tests

**System Dependencies:**
- **`bubblewrap`** (`bwrap`): required for unprivileged sandbox isolation during Reasoning Lease execution (Linux/WSL only).

**These dependencies must be installed in the user's local environment.**

> **⚠️ Mandatory Rule for Providers:**
> Before executing the initial setup (Cold Start) skill for the first time, the provider **MUST ask the user for explicit permission** to install these dependencies.
>
> 1. Provider detects that dependencies are missing.
> 2. Provider halts and prompts the user: *"openyggdrasil requires Python dependencies (listed in requirements) to be installed locally. Do you allow this?"*
> 3. Only upon user approval, the provider installs the requirements. **Silent or unprompted installations are strictly forbidden.**

### 3. Session-Scoped Cold Start

Once dependencies are approved and installed, the provider can execute the skill entrypoints defined in `SKILL.md`. The openyggdrasil runtime **cold-starts per Provider Session**. There are no system-level background daemons, but Operator Sessions bound to a Provider Session may persist via Mailbox polling for the session's lifetime. They exit cleanly on timeout or Provider Session termination.

### 4. TMUX Live Witness Policy

TMUX is an optional **live witness surface** for humans. It exists so a user can visually inspect the decision flow across Provider Sessions and Operator Sessions while a live verification run is in progress.

TMUX is **not** the core execution path. The default operating mode remains background-first:

- Provider and Operator Sessions run through the Mailbox, receipts, event logs, and provider-owned background tasks.
- Producer/Consumer work must continue even when no TMUX pane is attached.
- TMUX panes may tail the same logs, inboxes, receipts, or status snapshots that the background runtime already produces.
- Closing or failing a TMUX pane is an observability loss, not a memory-engine failure.
- A TMUX capture may be used as human-readable evidence, but it must not replace machine-readable receipts, schema-valid traces, or test results.

Status terms must stay precise:

| Status | Meaning |
|---|---|
| `background_task_passed` | The provider/operator work completed through the normal background path. |
| `tmux_visual_witness_available` | A human can inspect the live flow in TMUX. |
| `tmux_visual_witness_unavailable` | The visual witness is unavailable; the background path may still be healthy. |
| `foreground_equivalent` | The system was verified through background logs/receipts, not a true live foreground surface. |
| `live_foreground_claimed` | Allowed only when an actual foreground/live provider surface was verified. |

Provider adapters may implement TMUX dashboards differently, but they must not make TMUX a hard dependency of the provider-neutral runtime.

### Verify Installation Manually

If you prefer to verify the installation before attaching a provider:

```bash
# Clone the repository
git clone https://github.com/INTEGRITY2077/openyggdrasil.git
cd openyggdrasil

# Install dependencies (user-initiated)
pip install -r requirements.txt # (assuming requirements exist)

# Run import smoke test
python runtime/import_smoke.py
```



**Actual Codebase Implementation (Frontmatter Parser):**
The codebase includes `runtime/retrieval/skill_frontmatter_parser.py` to extract `---` YAML frontmatter from markdown files and validate it against a JSON Schema contract. Graphify and Pathfinder should rely on this parsed topological data before treating relationships as support evidence.

**Vault Promotion Rules — To be recorded:**
- Must be persistent, non-trivial, hard to re-derive, and reusable in future sessions.
- Transient conversations, trivial responses, and raw session dumps are strictly prohibited.

#### Graphify: The Derived Visibility Layer

This is a **derived layer** that builds graph/wiki/index views over the Vault.
**Graphify failure should not block the core capture, lifecycle, or Mailbox path; this remains a support-verification gate, not a production-ready claim.**

**Why adopt Graphify:**

| Problem | Graphify's Solution |
|---|---|
| Unnavigable as Vault pages pile up | Visualizes relationships as a node/edge graph |
| "Where does this concept connect?" | Automatically detects topic clusters via NetworkX Louvain community detection |
| Lack of structural context in search | Identifies core hubs via God Node and Surprising Connection analysis |
| Dependency on external infra (Vector DBs) | Pure Python + NetworkX, runs locally offline |

**Graphify Derived Pipeline:**

```
  Vault (Canonical Memory)
       │
       │  stage_graphify_input.py
       │  → Stages promoted Vault pages into the input corpus
       │
       ▼
  ┌─ Graphify 7-Step Pipeline ───────────────────────────────┐
  │                                                          │
  │  detect    → Detects corpus files                        │
  │  extract   → Extracts AST/structure                      │
  │  semantic  → Extracts semantic relations (uses tokens)   │
  │  build     → Builds NetworkX graph                       │
  │  cluster   → NetworkX Louvain community detection        │
  │  analyze   → God Node, Surprising Connection analysis    │
  │  report    → GRAPH_REPORT.md + graph.json + graph.html   │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
       │
       ▼
  Derived Artifacts (Not SOT):
  ├── GRAPH_REPORT.md    # Analysis report
  ├── graph.json         # Machine-readable graph
  ├── graph.html         # Visual exploration interface
  └── summary.json       # Node/edge/community summary
```

**Core Boundary:**

```
  ┌───────────────────────────────────────────────────────┐
  │  Vault (SOT)                                          │
  │  • Canonical memory — the only Source of Truth        │
  │  • Lifecycle state (ACTIVE / SUPERSEDED / STALE)      │
  │  • Provenance tracking (source_ref, origin_locator)   │
  │  • Enforced frontmatter schema                        │
  └────────────────────┬──────────────────────────────────┘
                       │ Derivation (One-way)
                       ▼
  ┌───────────────────────────────────────────────────────┐
  │  Graphify (Derived View)                               │
  │  • Graph/wiki/index — Visibility layer                 │
  │  • Failure does not block the core pipeline            │
  │  • Provides hints to Pathfinder (verification required)│
  │  • Never mutates the Vault (Read-only)                 │
  └───────────────────────────────────────────────────────┘
```

Graphify artifacts enhance Pathfinder's retrieval quality, but
**Pathfinder must cross-verify Graphify hints against the original Vault before treating them as support evidence.**
If a relationship suggested by Graphify cannot be verified in the Vault, it must be treated as an untrusted hint rather than SOT.

---

## System Architecture

### Two-Sided Engine + CQRS Operator Session Loop (9th North Star)

Building on this philosophy, openyggdrasil treats memory as a **two-sided engine** — a **Production Side** that captures and curates knowledge, and a **Consumption Side** that retrieves and delivers it.

From the 9th North Star, background execution subjects are named **Operator Sessions**. The term "Session" emphasizes that each subject has a clear start/end lifecycle and a 1:1 pairing relationship with a Provider Session.
The Operator Session runs in **physically separated independent background processes** following the **CQRS (Command Query Responsibility Segregation)** principle, communicating with the Provider Agent only through the **Mailbox**.
```
  Provider (e.g., Hermes)
  Detects decisions during user conversation
       │
       │  Emits save-intent / query-intent
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    MAILBOX (JSONL)                       │
  │  (Sole communication channel between sessions)          │
  └────────────────┬───────────────────┬────────────────────┘
                   │  save-intent      │  query-intent
                   ▼                   ▼
  ┌───────────────────────────┐  ┌───────────────────────────┐
  │  Producer Operator Session│  │  Consumer Operator Session│
  │  (Independent background) │  │  (Independent background) │
  │                           │  │                           │
  │  SKILL composes PTC       │  │  SKILL composes PTC       │
  │  primitives for S-P-O     │  │  primitives for Vault     │
  │  extraction + Vault write │  │  search + formatting      │
  └───────────┬───────────────┘  └───────────┬───────────────┘
              │                              │
              ▼                              ▼
  ┌───────────────────────────┐  ┌───────────────────────────┐
  │     VAULT (SOT)           │  │  Receipt → Mailbox        │
  │  Produced nodes stored    │  │  → Provider receives      │
  └───────────────────────────┘  └───────────────────────────┘
```

**Key constraint:** Operator Sessions (Producer/Consumer) run in physically separate context windows (PIDs) from the Provider Session, with no shared memory.
The Mailbox (JSONL filesystem) is the only communication channel. Existing Mock/Mailbox POC evidence is bounded proof; it does not prove all-provider same UX or production readiness.

#### Session Definitions

| Term | Definition | Physical Boundary |
|---|---|---|
| **Provider Session** | The PID of a provider's conversation window | User runs 3 Hermes instances → 3 independent Provider Sessions |
| **Operator Session** | A background independent process spawned by the provider | Producer and Consumer are each separate Operator Sessions (CQRS) |

**Scaling Model:** When N providers each summon operators, up to **N×2** Operator Sessions exist simultaneously.

**Start Type Distinction:**

| Type | Meaning | When |
|---|---|---|
| **Cold Start (Setup)** | One-time. SKILL.md recognition, dependency installation, Vault initialization | After repo clone |
| **Session Start (Initial Summon)** | Provider worker summons operator for the first time today via SKILL | Provider session start |

**SKILL.md vs Mailbox Role Separation:**

| | SKILL.md | Mailbox |
|---|---|---|
| Nature | **Static** reminder | **Dynamic** state awareness channel |
| Role | Announces the operator's existence | Conveys the operator's current state |
| Limitation | Cannot tell current state | — |

SKILL alone cannot tell a provider "Is my operator alive? What has it processed?"
The **only channel** for a provider to be aware of its loosely-coupled operator's state is the Mailbox.
**Therefore, Mailbox Hygiene determines overall system health.**
### Production Side — "What to remember"

The production pipeline doesn't blindly store everything. It **distills**
provider signals into typed decision candidates, **evaluates** their worthiness,
**places** them in navigable topic structures, and **prunes** stale knowledge
through lifecycle transitions.

### Consumption Side — "What to deliver"

The consumption pipeline doesn't dump the entire vault. **Pathfinder** builds
explainable, lifecycle-aware, and **Provenance-tracked Bounded Support Bundles**.

Rather than just raw text summaries, these bundles (governed by the `support_bundle.v1.schema.json` contract) structurally embed a **3-tier provenance tracking mechanism** that lets the agent trace back toward the original context:
1. **Breadcrumbs (`source_paths`)**: The array of URI paths to the original files where the knowledge was extracted.
2. **Topology IDs (`episode_ids`, `claim_ids`)**: The contextual topological coordinates within Vault/Graphify where this knowledge was generated.
3. **Evidence Refs (`safe_ref`)**: Safe pointers to supporting logs or terminal execution evidence when available, allowing the agent to inspect the less-compressed source context if needed.

Consequently, the agent receives both the distilled summary and bounded evidence addresses for origin inspection, securely delivered via the typed **Mailbox** contract by **Postman**.


## PTC (Programmatic Tool Calling) Concept & Architecture

The production and consumption pipelines are being realigned around a **PTC (Programmatic Tool Calling)** architecture. Existing PTC IPC/sandbox/template paths are partial evidence; production/consumption kitchen split, typed egress, and sandbox fail-closed are still open gates.

**Source of Truth (SOT):**
This architecture is heavily inspired by Anthropic's [Programmatic Tool Calling](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/programmatic-tool-calling) (PTC) and the broader open-ended agentic loop (REPL) philosophy.

### Original Architecture (Claude PTC)

```
  ┌──────────────────────────────────────────────────────────────┐
  │          Anthropic Programmatic Tool Calling (PTC)           │
  │                                                              │
  │  1. Agent: Emits `server_tool_use` (name: code_execution)    │
  │  2. Sandbox: Starts executing Python script                  │
  │  3. Script: Calls `await target_tool()` internally           │
  │  4. API: Pauses Sandbox, emits `tool_use` to Host            │
  │     (payload: `caller: { type: code_execution_... }`)        │
  │  5. Host: Returns `tool_result`                              │
  │  6. Sandbox: Resumes execution, processes data (loops, etc.) │
  │  7. Sandbox: Emits `code_execution_tool_result`              │
  └──────────────────────────────┬───────────────────────────────┘
                                 │ Contract: allowed_callers=["code_execution..."]
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                     Host (Client Tools)                      │
  │             (Database, File system, APIs, etc.)              │
  └──────────────────────────────────────────────────────────────┘
```

The standard PTC paradigm allows the agent to freely write Python code within a sandbox to control multiple tools:
1. The agent autonomously writes a Python script containing loops and conditional logic.
2. The script executes, calling multiple tools sequentially and filtering intermediate data, saving tokens and latency.
3. While efficient and flexible, normalizing knowledge into a strict lifecycle memory system using this approach is highly unpredictable. It relies entirely on the logical integrity of the agent's on-the-fly script, making it vulnerable to runtime hallucinations.

### openyggdrasil's PTC Transformation — 26-Tool Palette + IPC Callback Loop

```
  ┌──────────────────────────────────────────────────────────────┐
  │               openyggdrasil (PTC Palette)                    │
  │                                                              │
  │  1. Provider: ygg generates LLM code templates for OP1/OP2   │
  │  2. Stub Generator: injects IPC preamble + 26 tool functions │
  │  3. Sandbox Executor: runs Python script in bwrap cleanroom  │
  │  4. IPC Server: calls host primitives via Unix Domain Socket │
  │  5. Tool composition: template combines only allowed          │
  │     production/consumption tools for the current role         │
  │  6. Result: output returned from sandbox, recorded as receipt │
  └──────────────────────────────┬───────────────────────────────┘
                                 │ Transport: Unix Domain Socket
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │      26 PTC Tool Palette (runtime/ptc/_preamble.py)          │
  │  SEARCH:  deep_search, search_vault                          │
  │  PROVENANCE: locate_region, select_topic_anchor,             │
  │    read_origin_claims, read_recent_claims, collect_claim_ids,│
  │    read_source_paths, assemble_support_bundle,               │
  │    assemble_unanchored_bundle                                │
  │  PRODUCTION: find_similar, suggest_placement,                │
  │    get_category_tree, check_conflicts                        │
  │  GRAPH: trace_evolution, get_community, rank_by_relevance    │
  │  CHAIN: extract_spo, create_edge, prune_node, validate_node  │
  │  CORE: get_all_nodes, get_node, save_note, get_edges         │
  └──────────────────────────────────────────────────────────────┘
```

openyggdrasil's PTC model has moved from the legacy **Typed PTC Engine** (JSON Execution Plan, 8-Tool Chain) toward a 26-tool palette plus IPC callback loop:

1. **Tool Palette:** 8 tools → 26 across 6 groups (SEARCH, PROVENANCE, PRODUCTION, GRAPH, CHAIN, CORE). Each tool includes affordance-based descriptions (`Use this when` / `Do NOT use when`) in the preamble.
2. **IPC Callback Loop:** Python code running inside a bwrap cleanroom calls host primitives via a Unix Domain Socket. production sandbox fail-closed and typed egress are still separate gates.
3. **Dual Path:** Producer/Consumer supports both a fixed chain (extract_decisions→build_vault_node→save_to_vault) and a PTC chain (`ygg tell --ptc op1`). Dual path support itself is not a production-ready claim.
4. **LLM Free Composition (current state):** The 26-tool surface exists, but the current PTC production path is still close to the `extract_spo → suggest_placement → save_note` template. Safe role-scoped free composition inside kitchens is a P1 gate.
5. **P1 realignment required:** production(write/mutate) kitchen and consumption(read/search/support) kitchen must be split. Consumption surfaces must not expose `save_note`, `create_edge`, or `prune_node` as default handles.

### Background: Why PTC over Vector DBs / ElasticSearch? (Token Efficiency)

Traditional RAG (Retrieval-Augmented Generation) approaches rely on Vector DBs or ElasticSearch to retrieve massive amounts of documents, dumping thousands or tens of thousands of text tokens directly into the agent's context window. This is **expensive, slow, and causes "Lost in the middle" hallucinations**.

The primary reason openyggdrasil abandoned heavy external infrastructure in favor of a **pure local-filesystem PTC architecture** is its **overwhelming token efficiency and structural filtering**:

- **Context Exclusion of Intermediate Data:** When the agent calls utility tools like `scan_topology` or `filter_lifecycle`, massive amounts of intermediate data (e.g., scanning 20 Vault documents) should remain outside the agent's context window. The data is processed, filtered, and aggregated within Python memory before a typed result is returned.
- **Elimination of Model Round-Trip Overhead:** Querying 10 knowledge nodes as independent tools consumes massive tokens because it invokes the LLM individually for each query. By using PTC to read 10 documents within a single code execution block and returning only a summarized conclusion, token usage is reduced by approximately **10x or more**.
- **Returning Only the Final Summary:** The agent is shielded from the vast noise of the search process. It only receives the final, highly refined `bounded support bundle`.


## Execution Model

openyggdrasil does not have its own LLM or API keys.
When a provider (Hermes, Claude Code, Cursor, etc.) enters this repository,
it reads **`SKILL.md`** at the root and executes the entrypoints defined
there using its own tokens.

```
  Provider Agent
       │
       │  Enters repo → discovers SKILL.md
       │
       ▼
  ┌──────────────────────────────────────────────────┐
  │  SKILL.md (Contract)                              │
  │                                                  │
  │  "To capture, run this Python script"             │
  │  "To retrieve, call this entrypoint"              │
  │  "Input shape is X, output shape is Y"            │
  └──────────────────────────────────────────────────┘
       │
       ▼
  Agent runs Python entrypoints via its own shell/tool-use
  → producer/consumer runs fixed chain (no reasoning needed) through pipeline
  → or PTC chain (`--ptc`) executes code from the 26-tool palette
```

Two things are borrowed from the provider:

| Borrowed | Description |
|---|---|
| **Execution context** | The agent's shell/tool-calling ability to run Python scripts |
| **Reasoning tokens** | The LLM reasoning capability required to pass PTC contract guardrails and make complex decisions |

**The Operator Session is the intended pipeline execution subject.** Some utility paths run deterministically in pure Python, while decision-heavy guardrails require an explicit reasoning-lease boundary. This does not mean the full PTC kitchen is production-ready.

Independent API key configuration for self-hosted execution (without a
provider) is planned for the future.

---
## Operational Flow — Trigger to Delivery

The diagram above shows the internal chain, but the real question is:
**how does a provider actually invoke this system?**

There are two distinct invocation paths — one for **writing** knowledge
(Production Trigger) and one for **reading** it (Consumption Trigger).

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │              TARGET LIFECYCLE OVERVIEW (GATES STILL OPEN)               │
  │                                                                        │
  │  ① Provider reads SKILL.md                                             │
  │  ② Provider adapter/worker decides: "capture" or "retrieve"            │
  │                                                                        │
  │  CAPTURE PATH (Production)                RETRIEVE PATH (Consumption)  │
  │  ─────────────────────────                ──────────────────────────── │
  │  ③ Agent calls capture entrypoint         ③ Agent calls retrieve       │
  │     with structured signal                   entrypoint with query     │
  │  ④ Signal → 12-module chain               ④ Pathfinder → Vault scan   │
  │  ⑤ Vault updated                          ⑤ Support bundle assembled  │
  │  ⑥ Postman → Mailbox receipt              ⑥ Mailbox → Agent receives  │
  │                                              bounded retrieval result  │
  └─────────────────────────────────────────────────────────────────────────┘
```

### Production Trigger — Context Recognition and Delegation (First-Pass)

Target UX: a Provider Agent or adapter should recognize when an architectural decision or debugging insight is **valuable enough to be recorded (wiki-fied)**. Current status does not claim Hermes-native automatic MemoryTicket hooks or provider natural async reflection are PASS.

When this need is explicitly detected or routed, the Provider Agent should avoid copy-pasting the entire heavy text block. Instead, it should consult `SKILL.md` to construct a lightweight `Session Structure Signal`. This signal acts as a shallow request, pairing a brief summary with bounded pointers to relevant evidence handles.

```
  Provider Agent (The main entity interacting with the user)
       │
       │  ① Identifies or receives a context worth wiki-fying
       │
       │  ② Reads SKILL.md to discover the entrypoint and rules
       │
       │  ③ Constructs the Session Structure Signal (Shallow Request):
       │     {
       │       provider_id:         "hermes"
       │       provider_session_id: "session-2026-04-30-abc123"
       │       trigger_type:        "hard_trigger"
       │       surface_reason:      "Decided to use gateway pattern..."
       │       turn_range:          { from: 12, to: 18 }
       │       source_ref:          { path_hint: "sessions/abc123.jsonl" } // evidence handle, not raw dump
       │     }
       │
       │  ④ Publishes Intent to Mailbox & spawns Operator asynchronously (Fire-and-Forget)
       │     → Provider immediately returns to user chat (Non-blocking)
       │
       ▼
  Operator Session (Runs in background, receiving request via Mailbox)
```

**Key rules:**
- **Pointer-Based Delegation (`source_ref` is mandatory):** The Provider Agent must not mutate or unnecessarily duplicate raw conversations. It must pass a `source_ref` pointing to the relevant `.jsonl` log or evidence handle. Signals missing this pointer are rejected by the Admission Gate.
- **Asynchronous Cold-Start (Non-blocking target):** openyggdrasil should not block the provider. The target path delegates through Mailbox/background execution and leaves a receipt when the job is done; this is still bounded by provider adapter support and receipt evidence.
- **Reasoning Lease:** The Operator needs intelligence to perform deep structuring (Distill/Evaluate) in the background. The Provider adapter must expose an explicit reasoning-lease boundary, such as scoped auth delegation or asynchronous multiplexing of task contracts emitted by the background Operator.



### Production Pipeline — CQRS Producer/Consumer + PTC Dual Path

> ⚠️ **15th realignment note:** PTC IPC/sandbox/template execution paths exist, but PTC production/consumption kitchen split, typed egress, and sandbox fail-closed are not closed. This section describes the current execution model and next gates; it is not a production-ready claim.

When a capture signal enters the system, it is not blindly handed off to an automated black box. This process is divided between the Provider Session and a dynamically leased Operator Session:

1. **Initial Context Recognition (Provider Adapter / Worker)**: The provider adapter or worker reads `SKILL.md` to route contexts worth remembering. It should construct an initial signal (`Session Structure Signal` containing `surface_reason` and `source_ref`) and inject it into the OpenYggdrasil runtime only when evidence is available.
2. **Deep Structuring (Operator Session)**: In the target flow, the runtime receives this request through the provider adapter's Reasoning Lease boundary and spawns an Operator Session. This Operator Session is **not** meant to be a fixed pipeline sequence. It is a **Role-Polymorphic Leased Executor** concept assigned specifically to knowledge production roles (Distiller, Evaluator, Amundsen, Gardener).

True to the nature of PTC, the Operator Session can **execute template code inside a bwrap sandbox** for its Producer/Consumer role. The safe target is not to mix all 26 tools into one surface, but to split production and consumption kitchens and enforce role-specific allowlists plus typed egress.

The tools provided to the Operator Session follow two execution paths:

1. **Contract Guardrails (Requires Reasoning)**: Consume the Operator Session's reasoning tokens. The Operator Session must make judgments (distillation, evaluation, classification), but the guardrails strictly enforce the JSON Schema output.
2. **Utility Tools (No Reasoning)**: Pure Python deterministic functions. The Operator Session just passes the verified payload from the previous step to normalize, save, and package data.

```
  Session Structure Signal (Injected by Provider Agent)
       │
       ▼
  PTC Operator Session (Role-Polymorphic Executor assigned to Knowledge Production)
       │
       │  ① OpenYggdrasil provides a Task Contract (Distiller/Amundsen/Gardener etc)
       │  ② Operator Session invokes tools inside the role-specific kitchen
       │
       ▼
  ┌─ PTC Engine (Runtime) — Allowlisted Tool Pool ───────────────────────────┐
  │                                                                          │
  │  [Contract Guardrails — Structure Operator Session's reasoning]          │
  │                                                                          │
  │  ┌─ distill_signal (Guardrail — Refers to Affordance Contract) ────────┐ │
  │  │  Deeply distill shallow signal into structural decisions            │ │
  │  │  Role: Guardrail (Consumes Operator Session's reasoning)             │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  │                                                  ▼                       │
  │  ┌─ evaluate_candidate (Guardrail) ────────────────────────────────────┐ │
  │  │  Judges promotion worthiness, dedupes, threshold gating             │ │
  │  │  Role: Guardrail (Consumes Operator Session's reasoning)             │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  │                                                  ▼                       │
  │  ┌─ classify_novelty (Guardrail) ──────────────────────────────────────┐ │
  │  │  Classifies category & new continent (novelty)                      │ │
  │  │  Role: Guardrail (Consumes Operator Session's reasoning)             │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  │                                                  ▼                       │
  │  [Utility Tools — Pure Python functions for packing & planting]          │
  │                                                                          │
  │  ┌─ stamp_provenance (Utility) ────────────────────────────────────────┐ │
  │  │  Engraves Tree Rings: stamps source_ref, origin_locator             │ │
  │  │  Role: Utility (Deterministic Python)                               │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  │                                                  ▼                       │
  │  ┌─ compose_seed (Utility) ────────────────────────────────────────────┐ │
  │  │  Combines upstream outputs into the final engraved Seed             │ │
  │  │  Role: Utility (Deterministic Python)                               │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  │                                                  ▼                       │
  │  ┌─ plant_to_vault (Utility) ──────────────────────────────────────────┐ │
  │  │  Physically plants the seed in the Vault, transitions lifecycle     │ │
  │  │  Role: Utility (Deterministic Python)                               │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  │                                                  ▼                       │
  │  ┌─ update_topology (Utility) ─────────────────────────────────────────┐ │
  │  │  Updates continent/topic/episode topology                           │ │
  │  │  Role: Utility (Deterministic Python)                               │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  │                                                  ▼                       │
  │  ┌─ deliver_receipt (Utility) ─────────────────────────────────────────┐ │
  │  │  Generates Mailbox receipt                                          │ │
  │  │  Role: Utility (Deterministic Python)                               │ │
  │  └─────────────────────────────────────────────────────────────────────┘ │
  └──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  Operator Session leaves a Receipt in the Mailbox and terminates (task complete)
```

### PTC Execution Plan — Default Strategy Example (Production)

The JSON Tool Plan below is a **default strategy example**. Data dependencies like `←distill` are natural, but PTC primitive composition must stay inside role-specific kitchen boundaries. This example describes a target shape; it does not mean every free composition is production-safe. *(For a concrete implementation example, see the [PTC Code Writing Example](#ptc-code-example) section.)*

The PTC engine orchestrates these tools using one of three modes, depending on the complexity of the signal:

| Mode | Condition | Execution Pattern |
|---|---|---|
| `deterministic` | Simple structural updates | Guardrails auto-pass (Rule-based) → Utility execution |
| `lease_backed_llm` | Complex signals / ambiguity | Guardrail reasoning (3x) → Utility execution |
| `typed_unavailable` | Lease rejection / LLM failure | Returns typed unavailable result — silent fallback forbidden |

If the Operator Session violates the **typed contracts** at any guardrail (e.g., trying to submit a string instead of an array), the chain should stop with a typed `stop_reason` rather than silently dropping data.

<a id="ptc-code-example"></a>
#### PTC Code Example

The current Producer PTC chain (`ygg tell --ptc op1`) can run a template like this inside a bwrap sandbox. This explains a save scenario; it does not prove the full PTC production kitchen is PASS:

```python
# PTC preamble injected by stub_generator.py (26 tool functions injected)
import json

def main():
    text = "The gateway pattern routes API requests through a single entry point"

    # 1. Extract SPO triples (CHAIN group)
    triples = extract_spo(text)
    if not triples:
        return result({"status": "no_triples_found"})

    # 2. Check similar nodes + suggest placement (PRODUCTION group)
    for triple in triples:
        subject = triple.get("subject", "")
        similar = find_similar(subject, limit=5)
        placement = suggest_placement(subject, content=triple.get("object", ""))

        # 3. Save to Vault (CORE group)
        category = placement.get("result", {}).get("suggested_category", "concepts")
        saved = save_note(subject, triple.get("object", ""), category=category)

    return result({"saved": len(triples), "category": category})

main()
```

While this script runs inside the bwrap cleanroom, each call to `extract_spo`, `find_similar`, `suggest_placement`, and `save_note` is routed via Unix Domain Socket to the host's `ipc_server.py`. The goal is to avoid putting intermediate data directly into LLM context and return typed results, but raw stdout debug-only conversion and typed egress validation are still separate gates.

### Reasoning Model Baseline & Limitations

In the PTC pipeline, the Operator Session invokes the 26-tool palette via IPC callbacks inside a bwrap sandbox. Each call through the Unix Domain Socket is validated by host-side primitives. This is enforced by openyggdrasil's **Contract Guardrails**.

To successfully navigate this highly constrained environment, the **Reasoning Model Baseline is a frontier-class instruction-following and code-reasoning model**.

**Typical LLM Failure Modes for Sub-par Models:**
- **Tool Selection Failure:** Unable to choose appropriate tools from the 26-tool palette, calling irrelevant tools and breaking the chain.
- **IPC Timeout:** Failing to handle Unix Socket responses correctly, resulting in `socket_unavailable` errors.
- **Hallucination & Step Skipping:** Arbitrarily skipping required data processing steps and attempting to terminate the pipeline with hallucinated results.

openyggdrasil is designed not to rely on the LLM's goodwill or autonomy. However, the current state does not claim “100% protection.” In production mode, sandbox unavailable must close as `typed_unavailable`, and runtime must enforce role allowlists plus typed egress. Until those gates close, PTC production-ready is not claimed.

---


### Consumption Trigger — How providers retrieve past knowledge

When a provider session needs context from past decisions — "What did we
decide about the gateway pattern?" — the provider's agent **invokes
openyggdrasil's Operator Session** to search the accumulated knowledge.

```
  Provider Agent (working on a new task)
       │
       │  ① Agent recognizes it needs past context
       │     e.g., "We discussed this pattern before..."
       │
       │  ② Reads SKILL.md → discovers the retrieval entrypoint
       │
       │  ③ Calls the retrieval entrypoint with a query:
       │     {
       │       query_text:  "What was the gateway contract design?"
       │       profile:     "yggdrasilfgpoc"
       │       session_id:  "session-2026-04-30-xyz789"
       │     }
       │
       │  ④ openyggdrasil cold-starts Pathfinder
       │     → Scans Vault for matching topics
       │     → Assembles bounded support bundle
       │     → Returns lifecycle-aware, provenance-tracked result
       │
       ▼
  Agent receives a Pathfinder Retrieval Result:
  {
    status:           "completed"
    pathfinder_bundle: {
      anchor_type:    "topic"
      topic_id:       "topic:gateway-contract"
      support_facts:  ["Decided to use provider-owned gateway..."]
      source_paths:   ["vault/queries/gateway-contract.md"]
    }
    lifecycle_records: [{ state: "ACTIVE", valid_from: "..." }]
  }
```

**Key rules:**
- The agent receives a **bounded support bundle**, not a raw Vault dump.
  Facts in the bundle are expected to carry provenance and lifecycle state.
- If the topic has been **SUPERSEDED** or **STALE**, the retrieval result
  should explicitly state this instead of presenting outdated context as current.
- **Source refs are required.** Retrieval results should include source refs or
  typed unavailable when source refs are missing.
- This is the **LLM Wiki** pattern: the provider doesn't re-derive knowledge
  from raw transcripts — it queries an incrementally built, lifecycle-managed
  knowledge surface.

### PTC Tool Palette — Consumption Kitchen Boundary

The Consumer Operator should assemble read/search/support bundles. It must not mutate the Vault. The current palette shape still needs a P1 kitchen split so production tools and consumption tools are not exposed as one default surface.

```
  Retrieval Query
       │
       ▼
  ┌─ PTC Consumption Kitchen ────────────────────────────────┐
  │  Operator writes role-scoped code → sandbox → IPC         │
  │  Each tool has affordance: "Use this when / Do NOT..."     │
  │                                                          │
  │  Search:  bm25_search, deep_search                       │
  │  Trace:   locate_region, select_topic_anchor,             │
  │           read_origin_claims, read_recent_claims,         │
  │           collect_claim_ids, read_source_paths,           │
  │           assemble_support_bundle,                        │
  │           assemble_unanchored_bundle                      │
  │  Mutation tools such as save_note, create_edge, and       │
  │  prune_node must not be default handles in consumption.   │
  └──────────────────────────────────────────────────────────┘
       │
       ▼
  Support Bundle returned. LLM context untainted.
  │  Searches Vault indices to find the closest match        │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 2. scan_topology (Utility) ─────────────────────────────┐
  │  Deterministic: scans Map Maker for connected topics     │
  │  Provides Graphify hints if available                    │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 3. verify_origin (Utility) ─────────────────────────────┐
  │  Deterministic: physical file existence check            │
  │  If source file is missing, stops with "origin_missing"  │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 4. filter_lifecycle (Utility) ──────────────────────────┐
  │  Deterministic: filters by state (Default: ACTIVE only)  │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 5. guard_product (Utility) ─────────────────────────────┐
  │  Deterministic: ensures no forbidden text patterns leak  │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 6. build_bundle (Guardrail) ────────────────────────────┐
  │  Operator Session constructs the final explainable context │
  │  Decides what facts are actually relevant to the query   │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 7. dispatch_mailbox (Utility) ──────────────────────────┐
  │  Deterministic: drops the bundle into inbox JSONL        │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
                                     Provider agent receives
                                   bounded, explainable context
```

### PTC Execution Plan (Consumption)

| Mode | Condition | Execution Pattern |
|---|---|---|
| `fast_path` | Exact match (Cache hit) | `resolve_anchor` skips LLM → Utility → Mailbox |
| `deep_search` | Vague query (e.g., "how did we do X?") | Operator Session scans topology → reads multiple pages → builds bundle |
| `graphify_assisted` | Cross-domain query | Uses Graphify hints for semantic search |

The consumption side **must not fabricate context**. If the Vault is empty,
Pathfinder returns an honest `anchor_type: "none"` result. If provenance
can't be verified, it stops with `origin_shortcut_missing`. The agent
receives enough evidence to inspect what it is getting and why.

Until the P1 kitchen split is complete, do not claim “LLM free composition PASS” or “Consumer kitchen PASS.”


### PTC Tool Design Principles (Affordance-Based)

The PTC palette is an LLM-facing surface. A tool is not defined only by its
function name or JSON schema; it also needs an affordance contract that tells a
provider or Operator Session when the tool is appropriate.

Every provider-facing or LLM-facing primitive should be documented in this
shape:

```text
Use this when:
Do not use this when:
If ambiguous:
Typed unavailable when:
Required evidence refs:
Hard nonclaims:
```

This is especially important for the production/consumption kitchen split:

| Kitchen | Allowed affordance | Hard boundary |
|---|---|---|
| Production | create, mutate, stamp, save, receipt | must carry `source_ref`, receipt, and schema evidence |
| Consumption | read, search, assemble support, explain provenance | must not expose Vault mutation tools as default handles |
| Shared utility | validate, normalize, classify, package typed result | must close as typed unavailable when evidence is missing |

Signature-only contracts are incomplete LLM-facing documentation. They may
exist as machine metadata, but they are not enough to guide a provider or leased
Operator Session.


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
| ⑫ | **Pathfinder** | Retrieves explainable support material | Retrieval results should carry provenance and lifecycle proof, or typed unavailable |

---
## Reasoning Lease

Some complex signals or ambiguous tradeoffs go beyond simple PTC tool calls—they require extended LLM reasoning with time budgets and isolation guarantees.

openyggdrasil is intended to handle this through the **Reasoning Lease** boundary. The `lease_backed_llm` mode is a target execution lane; production proof still depends on typed egress, role allowlists, receipts, and sandbox fail-closed behavior:

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
│  │ Sandbox         │  Untrusted code should run isolated   │
│  │ Isolation       │  Failure → typed unavailable/rollback │
│  └─────────────────┘                                     │
│           +                                               │
│  ┌─────────────────┐                                     │
│  │ Typed Contract  │  Results flow back through contracts  │
│  │ Integration     │  Not raw stdout or untyped artifacts  │
│  └─────────────────┘                                     │
└───────────────────────────────────────────────────────────┘
```

The Reasoning Lease should run in an unprivileged sandbox via the mandatory dependency `bubblewrap`; when sandboxing is unavailable, production execution must fail closed instead of claiming isolation.

---

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
└── vault/              # Canonical project memory
```

---

## Inspirations & Acknowledgements

openyggdrasil stands on the shoulders of two key ideas (see the 'LLM Wiki' pipeline implementation above).

### [Graphify](https://github.com/safishamsi/graphify) (v5)

Graphify provides the structural analysis layer — turning codebases and knowledge
into navigable graphs:

| Graphify Concept | openyggdrasil Absorption |
|---|---|
| `detect → extract → build_graph → cluster → analyze → report → export` pipeline | → `common/graphify/` derived view engine |
| NetworkX Louvain community detection | → Topic/community structure for Map Maker |
| Confidence labels (EXTRACTED / INFERRED / AMBIGUOUS) | → Provenance confidence in retrieval results |
| Pure Python, local, offline | → **No external infrastructure dependency** |

---

## Design Principles

1. **Memory is an engine, not a text pile.** Every piece of memory has a source,
   a lifecycle state, and a typed contract.

2. **Mechanical base, mandatory reasoning.** The pipeline's structural skeleton
   (schema validation, AST extraction, topological clustering) runs deterministically,
   but meaningful knowledge production (Distill, Semantic Edge) requires an
   explicit Reasoning Lease boundary.

3. **Provider-neutral by default.** No provider should get special access to the vault.
   Hermes, Codex, Claude Code, and future providers are intended to share the
   same provider-neutral contracts.

4. **No external infrastructure.** Pure Python, NetworkX for graphs, filesystem
   for storage. No database, no vector store, no Docker required for the base
   pipeline.

5. **Fail-closed, not fail-open.** When evidence is missing, the system reports
   typed unavailability — it never fabricates readiness.

6. **Derived views are never source of truth.** Graphify indexes, graph views,
   and wiki pages are derived surfaces. The vault is the only canonical surface.



## Contributing

Contributions are welcome. Please read the existing `contracts/` schemas before
proposing new module interfaces — the typed contract boundary is the most
important architectural decision in the project.

## License & Brand Guidelines

This project is open-source and released under the [Apache License 2.0](./LICENSE).
You are free to use, modify, and distribute the code under the terms of this license.

**Trademark & Brand Protection (Section 6):**
While the code is open-source, the brand names **"openyggdrasil"** and **"INTEGRITY2077"**, along with their associated logos and trade dress, are strictly protected. The Apache 2.0 License explicitly **does not grant** permission to use these trademarks.

If you fork or distribute a modified version of this project, you must change the name and cannot use the openyggdrasil or INTEGRITY2077 branding to identify your version.

See [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) for companion dependency notices.
