---
name: openyggdrasil
description: Attaches the current provider session to the shared OpenYggdrasil memory forest when the session needs durable memory, attachment repair, cold-start health checks, or session-bound inbox access.
---

# OpenYggdrasil Skill

This skill attaches a provider session to OpenYggdrasil through explicit
workspace-local contracts.

Use this skill when:

- a provider session should become visible to OpenYggdrasil;
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

OpenYggdrasil exists so multiple providers can attach to one shared memory
forest while preserving provider, profile, session, source, and lifecycle
boundaries.

## Public References

- repository overview: `README.md`
- public schemas: `contracts/`
- provider-neutral runtime: `runtime/`
- canonical memory surface: `vault/`
- Graphify companion stack: `common/graphify/`

Do not depend on private docs, raw provider sessions, or operator-local
materials during bootstrap.

## Repo-Owned Tools

Use these tools instead of inventing provider-local mutations:

- attachment validation: `runtime/attachments/validate_attachment.py`
- attachment repair: `runtime/attachments/repair_attachment.py`
- cold-start health check: `runtime/attachments/provider_cold_start_healthcheck.py`
- provider-native skill deployment: `runtime/attachments/deploy_skill.py`
- Hermes profile deployment: `runtime/attachments/deploy_hermes_profile_skill.py`

## Core Rules

### 1. Stay In The Current Workspace

Work only inside the current workspace unless the operator explicitly narrows a
different target root.

### 2. Preserve Provider Boundaries

Every attachment must remain:

- provider-bound;
- profile-bound;
- session-bound.

Do not invent a fake cross-provider session.

### 3. Prefer Symbolic Raw Reference

Do not copy whole provider raw session history into OpenYggdrasil by default.

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

## Success Condition

The skill is successful when:

- `.yggdrasil/` exists in the current workspace;
- cold-start health check is `ready`, or `degraded` with explicit non-blocking
  user help;
- provider/session attachment files are schema-compatible;
- the session is discoverable by OpenYggdrasil runtime;
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
