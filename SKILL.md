---
name: openyggdrasil
description: Attaches the current provider session to the shared openyggdrasil memory forest when the session needs durable memory, attachment repair, cold-start health checks, or session-bound inbox access.
---

# openyggdrasil Skill

This skill attaches a provider session to openyggdrasil through explicit
workspace-local contracts.

Use this skill when:

- a provider session should become visible to openyggdrasil;
- `.yggdrasil/` attachment artifacts do not exist yet;
- an existing attachment needs schema repair;
- a provider session needs a session-bound inbox;
- first-run environment health checks should explain whether the local runtime
  is ready, degraded, or not ready;
- durable memory is needed without collapsing provider provenance.

Do not use this skill to:

- bypass provider authentication;
- ask the user for API keys or OAuth credentials;
- create a global inbox;
- merge unrelated live sessions into one shared session;
- dump whole live transcripts into `vault/` by default.

## North Star

```text
do not guess the memory layer
attach to it explicitly
```

openyggdrasil exists so multiple providers can attach to one shared memory
forest while preserving provider, profile, session, source, and lifecycle
boundaries.

## Public References

- repository overview: `README.md`
- public schemas: `contracts/`
- provider-neutral runtime: `runtime/`
- canonical memory surface: `vault/`
- Graphify companion stack: `common/graphify/`

Do not depend on private docs, raw provider sessions, or human-local
materials during bootstrap.

## Repo-Owned Tools

Use these tools instead of inventing provider-local mutations:

- attachment validation: `runtime/attachments/validate_attachment.py`
- attachment repair: `runtime/attachments/repair_attachment.py`
- cold-start health check: `runtime/attachments/provider_cold_start_healthcheck.py`
- provider-native skill deployment: `runtime/attachments/deploy_skill.py`
- Hermes profile deployment: `runtime/attachments/deploy_hermes_profile_skill.py`
- Hermes Reasoning Lease bridge deployment:
  `runtime/attachments/deploy_hermes_reasoning_lease_bridge_skill.py`

## Execution Model

openyggdrasil is not a second hidden LLM. The active provider supplies the
reasoning token and calls repo-owned Python entrypoints through typed contracts.

Before running a production or consumption path:

1. identify the provider, profile, and session;
2. attach or health-check the session through the bootstrap checklist;
3. use typed refs instead of raw transcripts, credentials, provider state DB
   rows, local private paths, or prompt text;
4. consult the module effort contracts before leasing provider reasoning:
   `contracts/module_effort_requirement.v1.schema.json`,
   `contracts/module_effort_plan.v1.schema.json`, and
   `runtime/reasoning/module_effort_requirements.py`.

Provider effort vocabulary is normalized only through
`runtime/cultivation/provider_effort_vocabulary_normalization.py` and
`contracts/provider_effort_vocabulary_normalization.v1.schema.json`. Do not
claim raw provider effort strings are globally equivalent across providers.

Provider-relative reasoning effort is normalized through
`runtime/reasoning/provider_effort_normalizer.py` and
`contracts/provider_reasoning_effort_normalization.v1.schema.json`. A
below-baseline provider should receive stronger guidance and compensation
strategies for reasoning-heavy modules; an above-baseline provider may conserve
tokens by selecting one lower effort level when the normalizer says that is
safe.

## Core Rules

### 1. Stay In The Current Workspace

Work only inside the current workspace unless the user explicitly narrows a
different target root.

### 2. Preserve Provider Boundaries

Every attachment must remain:

- provider-bound;
- profile-bound;
- session-bound.

Do not invent a fake cross-provider session.

### 3. Prefer Symbolic Raw Reference

Do not copy whole provider raw session history into openyggdrasil by default.

Preserve raw provenance through:

- `source_ref`;
- `origin_locator`;
- provider/session identifiers.

### 4. Never Use A Global Inbox

Only use a session-bound inbox:

```text
.yggdrasil/inbox/<provider>/<profile>/<session>.jsonl
```

### 5. Do Not Invent Metadata

If provider metadata is not visible from the current session, do not guess it.
Use only observable metadata and conservative defaults where explicitly allowed.

### 6. Keep The Vault Canonical

- provider raw stays near the provider;
- workspace-local runtime state stays under `.yggdrasil/`;
- only promoted durable knowledge belongs in `vault/`.

## Bootstrap Checklist

1. Detect the current workspace root.
2. Run the cold-start health check on first install:
   - write or read the repo-local `.yggdrasil/healthcheck/...` marker;
   - report `ready`, `degraded`, or `not_ready`;
   - for degraded or not-ready states, include failed checks, retry/fallback
     attempts, and required user help.
3. Detect the current provider id.
4. Detect or conservatively assign `provider_profile` and
   `provider_session_id`.
5. Build `session_uid = <provider_id>:<provider_profile>:<provider_session_id>`.
6. Create or repair:
   - `provider_descriptor.v1.json`;
   - `session_attachment.v1.json`;
   - `inbox_binding.v1.json`;
   - `turn_delta.v1.jsonl`.
7. Validate generated artifacts before declaring success.

## Hermes Reasoning Lease Bridge

Use this only for the Hermes provider-skill path:

```text
Hermes provider skill -> openyggdrasil provider skill bridge -> Reasoning Lease typed handoff
```

Do not replace this with MCP, a generic command gateway, an agent adapter,
foreground `.env` injection, stdin injection, raw transcript copying, Hermes
source patching, credential/profile copying, or provider state DB harvesting.

Cold start:

```bash
python runtime/attachments/deploy_hermes_reasoning_lease_bridge_skill.py \
  --profile-name <hermes-profile> \
  --workspace-root <openyggdrasil-public-root> \
  --hermes-home <hermes-home> \
  --cold-start
```

Cold start may create the Hermes profile skill package, binding artifact, and
typed environment contract. These files are not live proof by themselves.

Warm start:

```bash
python runtime/attachments/deploy_hermes_reasoning_lease_bridge_skill.py \
  --profile-name <hermes-profile> \
  --workspace-root <openyggdrasil-public-root> \
  --hermes-home <hermes-home> \
  --warm-start-check
```

Warm start is check-only. It must not rewrite the skill package, binding
artifact, or environment contract.

Live invocation may be claimed only when Hermes voluntarily invokes the
installed `openyggdrasil-reasoning-lease-bridge` skill and returns typed refs
that satisfy:

- `contracts/hermes_provider_skill_bridge_entrypoint.v1.schema.json`
- `runtime/reasoning/hermes_provider_skill_bridge_entrypoint.py`

Required live refs include `typed_task_id`, `typed_result_ref` or
`typed_unavailable_ref`, before/after main-context-window refs, and Memory
Saver/Finder refs whenever Memory Saver/Finder usage is claimed.

## Capture (Production)

Use this when the provider determines knowledge should be durably preserved
beyond the current session.

Display names and compatibility ids:

```text
MS1 = Memory Saver 1 = legacy internal OP1
MF1 = Memory Finder 1 = legacy internal OP2
```

Use `ms1` and `mf1` only as `ygg` command targets after the cold-start health
check confirms `ygg` is available. Treat `MS1` and `MF1` as prose/display
labels, not standalone commands. Treat `OP1` and `OP2` as internal
compatibility ids only.

**Dual routing (equal authority):**

```text
memory/save request
  -> Hermes memory for current-session memory (built-in)
  -> ygg tell ms1 for durable Vault save (openyggdrasil)
```

Entrypoint:

```bash
ygg tell ms1 "Decision: <summary> ..."
ygg tell --ptc ms1 "Decision: <summary> ..."   # PTC composition path
```

Both paths must be triggered. Hermes memory handles the session scope;
openyggdrasil handles cross-session, cross-provider durability.
Neither replaces the other.

Verify with:

```bash
ygg status ms1   # Result Receipt check
```

## Retrieve (Consumption)

Use this when the provider needs to recall knowledge from the long-term Vault.

Use `MF1` / `Memory Finder 1` as the prose/display name. In command examples,
always keep the `ygg` prefix. Treat `OP2` as the legacy internal compatibility
id only.

Entrypoint:

```bash
ygg ask mf1 "query"
ygg ask --ptc mf1 "query"   # PTC deep_search path
```

Verify with:

```bash
ygg status mf1   # Result Receipt check
```

The Provider should use retrieved knowledge to continue its reasoning chain.
Memory (session) + Vault (cross-session) together form the complete recall surface.
## Success Condition

The skill is successful when:

- `.yggdrasil/` exists in the current workspace;
- cold-start health check is `ready`, or `degraded` with explicit non-blocking
  user help;
- provider/session attachment files are schema-compatible;
- the session is discoverable by openyggdrasil runtime;
- the inbox path is session-bound rather than global.

## Failure Condition

The skill is blocked when:

- the provider cannot write into the current workspace;
- the runtime does not expose enough session context to build a safe attachment;
- required files cannot be created or repaired without guessing hidden metadata;
- cold-start health check is `not_ready` after bounded retry and fallback
  routes.

## Final Instruction

Be conservative, schema-correct, and provenance-visible. Attach the session; do
not reinvent the memory system.
