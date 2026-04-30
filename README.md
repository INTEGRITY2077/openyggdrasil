<p align="center">
  <h1 align="center">🌳 openyggdrasil</h1>
  <p align="center">
    <strong>A provider-neutral memory engine for AI coding agents</strong>
  </p>
  <p align="center">
    <em>Not another RAG wrapper. A persistent, lifecycle-aware knowledge layer<br/>
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
  <a href="#quick-start">Quick Start</a> •
  <a href="#inspirations--acknowledgements">Inspirations</a>
</p>

> **⚠️ This project is under active live testing.**
> The architecture is designed and contracts are defined, but the end-to-end
> pipeline is not yet production-ready. Expect breaking changes, incomplete
> integrations, and rough edges. We're building in the open — contributions
> and feedback are welcome.

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

openyggdrasil takes a different approach.

### Cross-Provider Pollination

The most powerful feature of openyggdrasil is that it is a **"Shared Brain"** not locked into any specific tool.

- **Hermes writes:** In a Hermes session, you decide on an architecture and it gets recorded in the Vault. (Source: `provider_id: hermes`)
- **Claude Code reads and updates:** Days later, you open Claude Code. It searches for, reads the document Hermes wrote, and continues the work. If the decision changes, Claude pushes the old knowledge to `SUPERSEDED` and writes the new knowledge.
- **Hermes recognizes it again:** The next time Hermes connects, it doesn't read the stale knowledge it wrote in the past, but the updated knowledge maintained by Claude Code.

This is possible because all agents abandon their internal transcript formats and share the same canonical Vault specification—the **strict frontmatter schema (Markdown + YAML)** of openyggdrasil.

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
  → PTC Engine presents a Tool Set and an Execution Plan
  → Agent calls tools sequentially to pass through the pipeline
```

Two things are borrowed from the provider:

| Borrowed | Description |
|---|---|
| **Execution context** | The agent's shell/tool-calling ability to run Python scripts |
| **Reasoning tokens** | The LLM reasoning capability required to pass PTC contract guardrails and make complex decisions |

**The subagent IS the pipeline.** While some pipeline modules (Utility Tools) run deterministically in pure Python, core decisions (Contract Guardrails) execute by consuming the agent's own reasoning tokens.

Independent API key configuration for self-hosted execution (without a
provider) is planned for the future.

---

## Provider Integration & Setup

openyggdrasil operates as a cold-started skill attached to your AI provider (e.g., Hermes, Claude Code, Cursor). You do not need to start background daemons or manage separate server processes.

> **⚠️ Current Reasoning Model:**
> openyggdrasil currently **borrows the provider's reasoning tokens** to operate.
> It does not have its own API keys or LLM infrastructure.
> Support for independent API key configuration is planned for the future. 

### 1. How Providers Recognize openyggdrasil

Providers attach to openyggdrasil by reading the **`SKILL.md`** manifest at the repository root. To initiate the connection:
- Point your agent's skill configuration to the absolute path of `SKILL.md`.
- The agent reads this contract, which defines the exact entrypoints, command shapes, and boundaries for memory retrieval and capture.

### 2. System Requirements & Dependency Installation

openyggdrasil runs purely locally. The core runtime relies almost entirely on the Python Standard Library, but the Graphify-derived views and Sandbox isolations require the following minimal dependency stack:

**Supported Operating Systems:**
- **Windows / macOS / Linux**: Full support for the core memory pipeline (Vault curation, Graphify derived views, and Pathfinder retrieval).
- **Linux / WSL2 (Windows Subsystem for Linux)**: **Required.** The Reasoning Lease Sandbox depends on `bubblewrap` for unprivileged isolation, and this is a mandatory production dependency. Windows/macOS users must use WSL2 to satisfy this requirement.

**Core Prerequisite:**
- **`Python 3.10+`**: Must be installed and accessible in the local environment.

**Python Packages (via pip):**
- **`graphifyy`**: the core companion package for structural analysis and graph building
- **`networkx`**: for graph derivation, node indexing, and traversal
- **`leidenalg` & `igraph`**: for community detection and topic clustering
- **`jsonschema`**: for strictly validating provider contracts and mailbox schemas
- **`pyyaml`**: for reading/writing configuration and manifest files
- **`pytest`**: for local contract verification and smoke tests

**System Dependencies:**
- **`bubblewrap`** (`bwrap`): required for unprivileged sandbox isolation during Reasoning Lease execution (Linux/WSL only).

**These dependencies must be installed in the user's local environment.**

> **⚠️ Mandatory Rule for Providers:**
> Before executing the cold-start skill for the first time, the provider **MUST ask the user for explicit permission** to install these dependencies.
> 
> 1. Provider detects that dependencies are missing.
> 2. Provider halts and prompts the user: *"openyggdrasil requires Python dependencies (listed in requirements) to be installed locally. Do you allow this?"*
> 3. Only upon user approval, the provider installs the requirements. **Silent or unprompted installations are strictly forbidden.**

### 3. One-Touch Cold Start

Once dependencies are approved and installed, the provider can execute the skill entrypoints defined in `SKILL.md`. The openyggdrasil runtime **cold-starts itself on demand**, executes the required memory transaction, and shuts down cleanly.

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

## PTC (Programmatic Tool Calling) Concept & Architecture

The production and consumption pipelines of openyggdrasil operate on a **PTC (Programmatic Tool Calling)** architecture.

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

### openyggdrasil's Transformation (The Typed PTC Engine)

```
  ┌──────────────────────────────────────────────────────────────┐
  │               openyggdrasil (Typed PTC Engine)               │
  │                                                              │
  │  1. PTC Engine: Injects `JSON Execution Plan`                │
  │     (e.g., ["distill_signal", "evaluate_candidate", ...])    │
  │  2. Agent: Calls Tool #1 (Requires strict JSON Schema)       │
  │  3. Guardrail: Consumes reasoning tokens, validates payload  │
  │  4. Utility: Auto-executes deterministic Python downstream   │
  │  5. Pipeline: Returns `stop_reason` or completes chain       │
  └──────────────────────────────┬───────────────────────────────┘
                                 │ Contract: Strict JSON Schema / Typed Payloads
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                 openyggdrasil 8-Tool Chain                   │
  │          (Deterministic, Type-safe, Lifecycle-managed)       │
  └──────────────────────────────────────────────────────────────┘
```

openyggdrasil intentionally constrains this autonomy, internalizing it as a **Typed Chain**:

1. **Dismantling the Black Box:** Instead of an invisible automated 12-module background loop, every module is exposed as a single-purpose "Tool" that the subagent must explicitly call.
2. **Constraining Freedom (JSON Tool Plan):** The agent is forbidden from arbitrarily mixing tools or writing custom scripts. Instead, the PTC engine forces a contextual **Execution Plan** (JSON Tool Plan) upon the agent.
3. **Dual-Nature Tools:** Tools are categorized into 'Contract Guardrails' (which consume reasoning tokens and enforce strict schemas) and 'Utility Tools' (deterministic Python execution), optimizing the agent's cognitive load.

Consequently, openyggdrasil's PTC model restricts the agent's open-ended reasoning loop and enforces sequential tool execution according to a predefined JSON Execution Plan, ensuring data integrity by design.

### Background: Why PTC over Vector DBs / ElasticSearch? (Token Efficiency)

Traditional RAG (Retrieval-Augmented Generation) approaches rely on Vector DBs or ElasticSearch to retrieve massive amounts of documents, dumping thousands or tens of thousands of text tokens directly into the agent's context window. This is **expensive, slow, and causes "Lost in the middle" hallucinations**.

The primary reason openyggdrasil abandoned heavy external infrastructure in favor of a **pure local-filesystem PTC architecture** is its **overwhelming token efficiency and structural filtering**:

- **Context Exclusion of Intermediate Data:** When the agent calls utility tools like `scan_topology` or `filter_lifecycle`, massive amounts of intermediate data (e.g., scanning 20 Vault documents) are never loaded into the agent's context window. The data is processed, filtered, and aggregated purely within Python memory.
- **Elimination of Model Round-Trip Overhead:** Querying 10 knowledge nodes as independent tools consumes massive tokens because it invokes the LLM individually for each query. By using PTC to read 10 documents within a single code execution block and returning only a summarized conclusion, token usage is reduced by approximately **10x or more**.
- **Returning Only the Final Summary:** The agent is shielded from the vast noise of the search process. It only receives the final, highly refined `bounded support bundle`.

<a id="ptc-code-example"></a>
#### PTC Code Writing Example (Single Async Script)

To fulfill the JSON Execution Plan, the subagent writes and executes a **single asynchronous Python script** inside the sandbox. Here is an example of the actual script the LLM emits to traverse all 8 steps without model round-trips:

```python
import asyncio
import json

async def run_production_pipeline():
    # 1. Distill
    distilled = await distill_signal(raw_signal="...", context="...")
    
    # 2. Evaluate (Contract Guardrail)
    verdict = await evaluate_candidate(candidate=distilled)
    
    # Subagent's own logic: abort if guardrail fails
    if not verdict.get("is_worth_remembering"):
        print(json.dumps({"status": "aborted"}))
        return
        
    # 3. Classify
    route = await classify_novelty(candidate=distilled, verdict=verdict)
    
    # 4~7. Deterministic Utilities (pass-through only)
    stamped = await stamp_provenance(candidate=distilled, route=route)
    seed = await compose_seed(verdict=verdict, route=route, segment=stamped)
    vault_path = await plant_to_vault(seed=seed)
    await update_topology(seed=seed, vault_path=vault_path)
    
    # 8. Final Receipt
    receipt = await deliver_receipt(seed=seed, vault_path=vault_path)
    
    # Only this final print statement is returned to the LLM's context (saving 10x tokens)
    print(json.dumps({"status": "success", "receipt": receipt}))

asyncio.run(run_production_pipeline())
```

While this script runs inside the sandbox, massive intermediate data structures (`distilled`, `verdict`, etc.) exist solely in Python memory and never pollute the LLM's context window.

### Reasoning Model Baseline & Limitations

In the PTC pipeline, the subagent (LLM) must retain the complex `JSON Execution Plan` within its sandbox context, invoke 8 tools in precise order, and pass strict JSON schema constraints for each tool. This rigidity is enforced by openyggdrasil's **Contract Guardrails**.

To successfully navigate this highly constrained environment, the **Reasoning Model Baseline is frontier-class models like Claude 3.5 Sonnet or GPT-4o**.

**Typical LLM Failure Modes for Sub-par Models:**
- **Execution Plan Neglect:** Ignoring the enforced tool sequence and attempting to write arbitrary scripts to bypass the sandbox.
- **Guardrail Validation Failure:** Failing to adhere to strict JSON schemas, receiving an error from the `evaluate` tool, and falling into an error loop (Timeout/Lease Failed) due to an inability to self-correct.
- **Hallucination & Step Skipping:** Arbitrarily skipping required data processing steps and attempting to terminate the pipeline with hallucinated results.

openyggdrasil does not rely on the LLM's goodwill or autonomy. Even if a model ignores prompts and acts unpredictably, the main system (Vault) is 100% protected by the sandbox and strict type validations. Models that fail to meet this baseline are immediately filtered out during prior Readiness Governance, preventing them from claiming the `production_readiness_claimed` mark in the provider receipt (`hermes_routing_receipt`).

---

## How It Works

### Core Philosophy: Absorbing Karpathy's 'LLM Wiki' + Graphify Extension

openyggdrasil directly implements Andrej Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) concept as its system architecture. Instead of re-deriving knowledge via RAG on every query, the system is designed so that the **LLM incrementally builds and maintains a persistent wiki**.

To overcome the navigational limits of a simple flat wiki, the system dismantles and integrates the structural analysis pipeline from [Graphify (v5)](https://github.com/safishamsi/graphify) as a dynamic topological layer.

| LLM Wiki + Graphify Concept | openyggdrasil Pipeline Implementation |
|---|---|
| **Raw Sources** (immutable originals) | → Provider Signal (①) — original signals are never mutated |
| **The Wiki** (LLM-maintained knowledge) | → Vault — Canonical memory (SOT) with lifecycle states |
| **The Schema** (CLAUDE.md rules) | → `contracts/` — Machine-readable JSON Schema boundaries |
| **Ingest** operation | → Production Pipeline (Signal Capture → Evaluate → Topological Placement) |
| **Query** operation | → Consumption Pipeline (Topological Search → Provenance Bundle Assembly) |
| **Lint** operation | → Gardener Pruning + Amundsen Consistency Checks |
| **`index.md`** catalog | → Pathfinder's index-based retrieval |
| **`log.md`** chronology | → Source repository with temporal edges |
| *Graphify: Community Clustering* | → Topic clustering in Map Maker (Leiden algorithm) |
| *Graphify: Derived Network* | → `common/graphify/` — Offline derived views built on top of the static Vault |

> *"The wiki becomes richer with every source added. A human's job is to curate the sources and ask good questions. The LLM's job is everything else."* — Karpathy

openyggdrasil extends this beyond a simple wiki into a **multi-provider / multi-agent** architecture equipped with typed contracts, lifecycle governance, and a **pure-local offline graph layer** without relying on external infrastructure like Vector DBs.

Building on this philosophy, openyggdrasil treats memory as a **two-sided engine** — a **Production Side** that captures and curates knowledge, and a **Consumption Side** that retrieves and delivers it.

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                      PRODUCTION SIDE                        │
                    │                                                             │
  Provider Signal   │ ┌──────────────┐     ┌──────────────┐     ┌──────────────┐  │
  (Hermes, Claude) ─┼─▶│   Distill    │────▶│ **Evaluate** │────▶│ Plant/Commit │  │
                    │ │ (Structurize)│     │(Value & Schema│     │ (Record to   │  │
                    │ └──────────────┘     │  Validation)  │     │   Vault)     │  │
                    │                      └──────────────┘     └──────────────┘  │
                    └─────────────────────────────────┬───────────────────────────┘
                                                      │ (Only Type-Safe Seeds)
                                               ┌──────┴──────┐
                                               │    VAULT    │
                                               │ (SOT Memory)│
                                               └──────┬──────┘
                                                      │
                    ┌─────────────────────────────────┴───────────────────────────┐
                    │                      CONSUMPTION SIDE                       │
                    │                                                             │
  Retrieval Query   │ ┌──────────────┐     ┌──────────────┐     ┌──────────────┐  │
  (Needs Context)  ─┼─▶│  Pathfinder  │────▶│ **Mailbox**  │────▶│   Provider   │  │
                    │ │ (Explore &   │     │ (Delivery    │     │   Session    │  │
                    │ │ Bundle build)│     │  Contract)   │     │(Context Load)│  │
                    │ └──────────────┘     └──────────────┘     └──────────────┘  │
                    └─────────────────────────────────────────────────────────────┘
```

### Core Pipeline Flow

```text
[ Production Pipeline ]                       [ Consumption Pipeline ]
Provider Signal                               Provider Query
       │                                             │
       ▼                                             ▼
  1. Distill                                    1. Pathfinder (Topology Scan)
  2. Evaluate          ──(Vault SOT)──          2. Resolve (Surface Read)
  3. Place             ──(Graphify)──           3. Support Bundle (Provenance)
  4. Prune                                      4. Postman (Mailbox Receipt)
```

### Production Side — "What to remember"

The production pipeline doesn't blindly store everything. It **distills**
provider signals into typed decision candidates, **evaluates** their worthiness,
**places** them in navigable topic structures, and **prunes** stale knowledge
through lifecycle transitions.

### Consumption Side — "What to deliver"

The consumption pipeline doesn't dump the entire vault. **Pathfinder** builds
explainable, lifecycle-aware, and **Provenance-tracked Bounded Support Bundles**.

Rather than just raw text summaries, these bundles (governed by the `support_bundle.v1.schema.json` contract) structurally embed a **3-tier provenance tracking mechanism** to allow 100% context restoration:
1. **Breadcrumbs (`source_paths`)**: The array of URI paths to the original files where the knowledge was extracted.
2. **Topology IDs (`episode_ids`, `claim_ids`)**: The contextual topological coordinates within Vault/Graphify where this knowledge was generated.
3. **Evidence Refs (`safe_ref`)**: Safe pointers to the exact Raw Conversation Logs or terminal execution transcripts, allowing the agent to immediately trace back to the uncompressed reality if needed.

Consequently, the agent receives both the distilled summary and the exact address to return to its origin, securely delivered via the typed **Mailbox** contract by **Postman**.

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

**Actual Codebase Implementation (Frontmatter Parser):**
This is not merely theoretical documentation. The system actively utilizes `runtime/retrieval/skill_frontmatter_parser.py` to extract the `---` YAML frontmatter from all markdown files and rigorously validates it against a strict JSON Schema contract. Both Graphify and Pathfinder rely on this parsed topological data to construct their mathematical search networks.

**Vault Promotion Rules — To be recorded:**
- Must be persistent, non-trivial, hard to re-derive, and reusable in future sessions.
- Transient conversations, trivial responses, and raw session dumps are strictly prohibited.

#### Graphify: The Derived Visibility Layer

This is a **derived layer** that builds graph/wiki/index views over the Vault.
**Even if Graphify fails, the core pipeline (capture, lifecycle, Mailbox) is unaffected.**

**Why adopt Graphify:**

| Problem | Graphify's Solution |
|---|---|
| Unnavigable as Vault pages pile up | Visualizes relationships as a node/edge graph |
| "Where does this concept connect?" | Automatically detects topic clusters via Leiden community clustering |
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
  │  cluster   → Leiden community clustering                 │
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
**Pathfinder always cross-verifies Graphify hints against the original Vault.**
If a relationship suggested by Graphify cannot be verified in the Vault, it is ignored.

---

## Operational Flow — Trigger to Delivery

The diagram above shows the internal chain, but the real question is:
**how does a provider actually invoke this system?**

There are two distinct invocation paths — one for **writing** knowledge
(Production Trigger) and one for **reading** it (Consumption Trigger).

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    FULL LIFECYCLE OVERVIEW                              │
  │                                                                        │
  │  ① Provider reads SKILL.md                                             │
  │  ② Provider's agent decides: "capture" or "retrieve"                   │
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

### Production Trigger — How providers capture knowledge

When a provider session produces a decision worth remembering — a design
choice, a debugging insight, a resolved trade-off — the provider's agent
**invokes openyggdrasil as a skill** to capture it.

```
  Provider Agent (e.g., Hermes, Claude Code, Cursor)
       │
       │  ① Reads SKILL.md from the openyggdrasil repo root
       │     → Discovers entrypoints, input shapes, boundaries
       │
       │  ② Constructs a Session Structure Signal:
       │     {
       │       provider_id:         "hermes"
       │       provider_session_id: "session-2026-04-30-abc123"
       │       trigger_type:        "hard_trigger"
       │       surface_reason:      "Decided to use gateway pattern..."
       │       turn_range:          { from: 12, to: 18 }
       │       source_ref:          { path_hint: "sessions/abc123.jsonl" }
       │     }
       │
       │  ③ Calls the capture entrypoint defined in SKILL.md
       │     → openyggdrasil cold-starts, processes the signal, shuts down
       │
       ▼
  openyggdrasil Production Pipeline receives the signal
```

**Key rules:**
- The provider agent **must read `SKILL.md`** to discover valid entrypoints.
  It never guesses or hard-codes internal paths.
- The signal must carry a **`source_ref`** — provenance is mandatory, not
  optional. Signals without source references are rejected at the gate.
- openyggdrasil **cold-starts on demand**. There is no background daemon.
  The provider calls it, it runs, it exits.

### Production Pipeline — Subagent's 8-Tool Chain

When a capture signal enters the system, the subagent does not just blindly hand it off to an automated black box. **The subagent explicitly invokes the following 8 tools sequentially** via the PTC engine.

These tools have a dual nature:

1. **Contract Guardrails (3 Tools)**: Consume the subagent's reasoning tokens. The subagent must read the source material, judge it, and format it into a structured schema to pass the tool.
2. **Utility Tools (5 Tools)**: Pure Python deterministic functions. The subagent just passes the verified payload from the previous step without spending reasoning tokens.

```
  Session Structure Signal
       │
       ▼
  ┌─ 1. distill_signal (Guardrail) ──────────────────────────┐
  │  Subagent reads raw signal and structures the decision   │
  │  Extracts: rationale, alternatives, confidence_score     │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 2. evaluate_candidate (Guardrail) ──────────────────────┐
  │  Subagent judges promotion worthiness                    │
  │  "Is this syntactically valid and worth remembering?"    │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 3. classify_novelty (Guardrail) ────────────────────────┐
  │  Subagent classifies category & novelty                  │
  │  "Is this topic known or a new continent?"               │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 4. stamp_provenance (Utility) ──────────────────────────┐
  │  Deterministic: stamps source_ref, turn_range, dedup_key │
  │  Output: preserved segment with planting_ready flag      │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 5. compose_seed (Utility) ──────────────────────────────┐
  │  Deterministic: combines guardrail outputs + provenance  │
  │  Creates the final `engraved_seed`                       │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 6. plant_to_vault (Utility) ────────────────────────────┐
  │  Deterministic: executes the filesystem write            │
  │  Handles ACTIVE → SUPERSEDED transitions automatically   │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 7. update_topology (Utility) ───────────────────────────┐
  │  Deterministic: updates Map Maker's bridge topology      │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ 8. deliver_receipt (Utility) ───────────────────────────┐
  │  Deterministic: generates the final delivery receipt     │
  │  Records clearinghouse event in the Mailbox              │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
                                          Vault updated
```

### PTC Execution Plan (Production)

The subagent receives a JSON Tool Plan and fulfills it by writing a single asynchronous Python script to execute inside the sandbox. *(For a concrete implementation example, see the [PTC Code Writing Example](#ptc-code-example) section above.)*

The PTC engine orchestrates these 8 tools using one of three plans, depending on the complexity of the signal:

| Mode | Condition | Execution Pattern |
|---|---|---|
| `deterministic` | Simple structural updates | Guardrails auto-pass (Rule-based) → Utility execution |
| `lease_backed_llm` | Complex signals / ambiguity | Full reasoning (3x HIGH) → Utility execution |
| `fallback` | Lease rejection | Downgrade to safe baseline or halt pipeline |

If the subagent violates the **typed contracts** at any guardrail (e.g., trying to submit a string instead of an array), the chain stops with a typed `stop_reason`—it never silently drops data.

### Consumption Trigger — How providers retrieve past knowledge

When a provider session needs context from past decisions — "What did we
decide about the gateway pattern?" — the provider's agent **invokes
openyggdrasil as a subagent** to search the accumulated knowledge.

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
  Every fact in the bundle carries provenance and lifecycle state.
- If the topic has been **SUPERSEDED** or **STALE**, the retrieval result
  explicitly states this — the agent is never silently given outdated context.
- **Source refs are required.** The retrieval result always links back to
  the original provider session that produced the knowledge.
- This is the **LLM Wiki** pattern: the provider doesn't re-derive knowledge
  from raw transcripts — it queries an incrementally built, lifecycle-managed
  knowledge surface.

### Consumption Pipeline — Pathfinder's 7-Tool Chain

Retrieval is also not an automatic black box. The subagent invokes the following 7 tools sequentially to fetch and verify knowledge.

```
  Retrieval Query
       │
       ▼
  ┌─ 1. resolve_anchor (Guardrail) ──────────────────────────┐
  │  Subagent determines the topic anchor from the query     │
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
  │  Subagent constructs the final explainable context       │
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
| `deep_search` | Vague query (e.g., "how did we do X?") | Subagent scans topology → reads multiple pages → builds bundle |
| `graphify_assisted` | Cross-domain query | Uses Graphify hints for semantic search |

The consumption side **never fabricates context**. If the Vault is empty,
Pathfinder returns an honest `anchor_type: "none"` result. If provenance
can't be verified, it stops with `origin_shortcut_missing`. The agent
always knows exactly what it's getting and why.

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

Some complex signals or ambiguous tradeoffs go beyond simple PTC tool calls—they require extended LLM reasoning with time budgets and isolation guarantees.

openyggdrasil handles this via the **Reasoning Lease** layer. It activates when the PTC engine's `lease_backed_llm` mode is used:

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

The Reasoning Lease runs in an unprivileged sandbox via the mandatory dependency `bubblewrap`, ensuring that the subagent's complex autonomous loop cannot corrupt the main system.

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
| NetworkX + Leiden community clustering | → Topic/community structure for Map Maker |
| Confidence labels (EXTRACTED / INFERRED / AMBIGUOUS) | → Provenance confidence in retrieval results |
| Pure Python, local, offline | → **No external infrastructure dependency** |

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

## Current State — Live Testing

> **This project is not production-ready.** We are live-testing the architecture
> and iterating in public.

The module chain architecture is designed with 37,000+ lines of runtime code
and 510+ passing tests — but the end-to-end pipeline does not yet pass through
from signal to mailbox.

**What exists:**
- 12-module chain contract definitions and internal logic
- Provider-neutral capture, evaluation, cultivation, and retrieval implementations
- Pathfinder retrieval with PTC (Programmatic Tool Calling) support
- Graphify-derived snapshot views
- Hermes provider adapter (foreground)

**What does not work yet:**
- Top-level facade wiring (35 stubs need to be connected to internal logic)
- End-to-end pipeline pass-through (signal → mailbox)
- Mailbox async delegation loop
- Bubblewrap sandbox runner integration
- Safe provider-owned gateway contract

See the [SKILL.md](./SKILL.md) for the provider-facing operating contract.

---

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
