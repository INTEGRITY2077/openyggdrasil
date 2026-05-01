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
  <a href="#🤖-ai-agent--provider-guidelines">AI Agent Guidelines</a> •
  <a href="#👨‍💻-getting-started-for-humans">Getting Started</a> •
  <a href="#🧠-architecture--core-concepts">Architecture</a> •
  <a href="#📊-current-status--architecture-alignment-scorecard">Scorecard</a>
</p>


## 🤖 AI Agent & Provider Guidelines

This section serves as the **highest-priority behavioral directive (LLM-Facing Affordance)** for Provider Agents operating within openyggdrasil. If you are an AI agent reading this, you must adhere to the following rules.

### 1. Provider Entrypoint (SKILL.md)
Providers connect to openyggdrasil by reading the **`SKILL.md`** manifest at the repository root.
- Set your skill configuration to the absolute path of `SKILL.md`.
- Reading `SKILL.md` reveals the exact entrypoints, command formats, and boundaries for memory search and capture.

### 2. Prohibition of Unauthorized Dependency Installation (Absolute Rule)
> **⚠️ Mandatory Provider Rule:**
> Before running the cold-start skill for the first time, the provider **MUST ask for the user's explicit permission**.
> 1. If missing dependencies are detected, halt and prompt the user: *"openyggdrasil requires Python dependencies to be installed locally. Proceed?"*
> 2. Only install dependencies upon user approval. **Silent or promptless installation is strictly prohibited.**

### 3. Vault Promotion Rules (What to Record)
Not every conversation is recorded. To be written to the Vault, knowledge must be persistent, non-trivial, difficult to re-derive, and reusable in future sessions. Temporary chats, trivial responses, and raw session dumps are strictly prohibited from being recorded.

### 4. Prohibition of Unauthorized PTC Pipeline Execution

To fulfill the JSON Execution Plan, the subagent will eventually write and execute a **single asynchronous Python script** inside the sandbox. Here is an example of the future script the LLM will emit to traverse all 8 steps without model round-trips:

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

### 📊 Current Status — Architecture Alignment Scorecard (2026-05-01 15:40 KST, Phase 8 Target: E12D, R14→R15)

> **⚠️ This project is not production-ready.**
> We are live-testing the runtime and iterating in the open towards the 8th Roadmap (PTC-based Target Architecture).
> **Effort normalizer has been officially retired** and replaced by a Persona document-based architecture.

The table below quantifies the alignment between the architecture described in this README and the actual implementation. To prevent misunderstanding, the current state of each block is explicitly labeled with 4 levels (LIVE / PARTIAL / STUB / ABSENT).

| Rating | Meaning |
|---|---|
| 🟢 **LIVE** | Runtime code exists, tests PASS, or core verification complete |
| 🟡 **PARTIAL** | Code/Contracts exist, but end-to-end trace is unverified or Subagent integration is WIP |
| 🟠 **STUB** | File/Concept exists, but only stub code is present |
| 🔴 **ABSENT** | No code exists; only design documents exist |

#### Production Side
| Module | Status | Remarks |
|---|---|---|
| Session Structure Signal | 🟢 LIVE | Tree Rings established. Same-Run Typed Ref Source verified |
| Admission Gate | 🟡 PARTIAL | `source_ref` contract verification works. Quality Gate P0 issue raised |
| Distiller | 🟡 PARTIAL | Guardrail + Persona exist. e12c R14 PASS, R15 in progress |
| Evaluator | 🟡 PARTIAL | PTC Execution Trace Packet builder implemented |
| Amundsen | 🟡 PARTIAL | Continent branching schema + runtime + Persona implemented |
| Map Maker | 🟡 PARTIAL | Topology calculation + Persona implemented. NetworkX (BSD-3) Louvain clean-room integration complete |
| Gardener | 🟡 PARTIAL | Physical planting + **new Persona added**. Auto-healing incomplete |
| Postman | 🟡 PARTIAL | Runner Source Packet Producer committed (`37b2dac`). R14 37 tests PASS |
| Content Hash Protection | 🟠 STUB | P1 issue and design proposal raised |
| Rejection Loop | 🟠 STUB | P1 issue raised. No runtime code yet |

#### Consumption Side
| Module | Status | Remarks |
|---|---|---|
| Pathfinder | 🟡 PARTIAL | Persona exists. Tool-based scan + 7 PTC tools defined |
| Support Bundle | 🟡 PARTIAL | 3-tier Tree Ring tracking. Cross-Provider verification PASS |
| Mailbox | 🟠 STUB | Schema exists. **Receipt Consumer Persona newly added** |
| Lifecycle Filter | 🟢 LIVE | Frontmatter parsing and ACTIVE/SUPERSEDED state filtering works perfectly |

#### Infrastructure / Cross-Cutting
| Module | Status | Remarks |
|---|---|---|
| SKILL.md Cold Start | 🟢 LIVE | Automatic provider recognition & entrypoint calling works |
| Typed PTC Engine | 🟡 PARTIAL | **`engine.py` 2,586 lines.** 5-stage invocation chain implemented. R14 PASS, R15 live |
| Persona System (9 roles) | 🟢 LIVE | 9 Personas complete (replaced effort normalizer) |
| Reasoning Lease | 🟡 PARTIAL | Delegation contract works. Bubblewrap Sandbox Stub pending (R15 Blocker) |
| Vault (SOT) | 🟢 LIVE | Directory constraints & frontmatter validation fully operational |
| Graphify Derived View | 🟡 PARTIAL | Community derivation scripts functional (GPL dependencies removed) |
| Cross-Provider | 🟡 PARTIAL | Cross-memory access tests PASS |
| Hermes Adapter | 🟡 PARTIAL | e12c R14 PASS (37 tests). R15 in progress |
| i18n Pipeline | 🔴 ABSENT | P1 issue raised. No backend language code path |
| Inline Source Marking | 🔴 ABSENT | File-level tracking only |
| Atomic Rollback | 🟠 STUB | Dulwich Porcelain-based Atomic Vault Writer POC (testbed) complete |

#### Alignment Summary
| Domain | Total | 🟢 LIVE | 🟡 PARTIAL | 🟠 STUB | 🔴 ABSENT | Alignment |
|---|---|---|---|---|---|---|
| Production | 10 | 1 | 7 | 2 | 0 | 80% |
| Consumption | 4 | 1 | 2 | 1 | 0 | 75% |
| Infrastructure | 11 | 3 | 5 | 1 | 2 | 75% |
| **Total** | **25** | **5** | **14** | **4** | **2** | **78%** |


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
