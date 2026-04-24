---
name: openyggdrasil
description: Attaches the current provider session to the shared OpenYggdrasil memory forest when the session needs durable memory, attachment repair, or session-bound inbox access.
---

# OpenYggdrasil Skill

This skill attaches the current provider session to the shared OpenYggdrasil
memory forest through explicit workspace-local contracts.

Use this skill when:

- the current provider session should become visible to OpenYggdrasil
- `.yggdrasil/` artifacts do not exist yet for this workspace/session
- an existing attachment needs repair to match canonical contracts
- a provider session needs a session-bound inbox binding
- a session needs durable memory without collapsing provenance

Do not use this skill to:

- bypass provider authentication
- proxy provider OAuth into third-party tools
- create a global inbox
- merge unrelated live sessions into one shared session
- dump whole live transcripts into `vault/` by default

## North Star

OpenYggdrasil exists to let many providers attach to one shared memory forest
through explicit contracts.

Short rule:

```text
do not guess the memory layer
attach to it explicitly
```

## Canonical References

This skill is self-contained on purpose.

Do not depend on `doc/` when attaching or repairing a session. Treat `doc/`
as repo-managed documentation, not as a deploy/runtime requirement.

## Validation And Deployment Tools

Use these repo-owned tools instead of inventing provider-local mutations.

- attachment validation:
  - `runtime/attachments/validate_attachment.py`
- attachment repair:
  - `runtime/attachments/repair_attachment.py`
- provider-native skill deployment:
  - `runtime/attachments/deploy_skill.py`

## Core Rules

### 1. Stay In The Current Workspace

Work only inside the current workspace unless the operator explicitly narrows a
different target root.

### 2. Preserve Provider Boundaries

Do not invent a fake cross-provider session.

Every attachment must remain:

- provider-bound
- profile-bound
- session-bound

### 3. Prefer Symbolic Raw Reference

Do not copy whole provider raw session history into OpenYggdrasil by default.

If raw provenance can be referenced, preserve it through:

- `source_ref`
- `origin_locator`
- provider/session identifiers

### 4. Never Use A Global Inbox

Only use a session-bound inbox.

### 5. Do Not Invent Metadata

If provider metadata is not visible from the current session, do not guess it.
Use only what is observable and conservative defaults where explicitly allowed.

### 6. Keep The Vault Canonical

The default rule is:

- provider raw stays near the provider
- workspace-local runtime state stays under `.yggdrasil/`
- only promoted durable knowledge belongs in `vault/`

## Quick Bootstrap Checklist

When this skill is used for bootstrap:

1. Detect the current workspace root.
2. Detect the current provider id.
3. Detect or conservatively assign:
   - `provider_profile`
   - `provider_session_id`
4. Build:
   - `session_uid = <provider_id>:<provider_profile>:<provider_session_id>`
5. Create or repair:
   - `provider_descriptor.v1.json`
   - `session_attachment.v1.json`
   - `inbox_binding.v1.json`
   - `turn_delta.v1.jsonl`
6. Keep the inbox session-bound:
   - `.yggdrasil/inbox/<provider>/<profile>/<session>.jsonl`
7. Validate the generated artifacts before declaring success.

## Success Condition

The skill is successful when:

- `.yggdrasil/` exists in the current workspace
- provider/session attachment files are schema-compatible
- the session is discoverable by OpenYggdrasil runtime
- the inbox path is session-bound rather than global

## Failure Condition

The skill is blocked when:

- the provider cannot write into the current workspace
- the runtime does not expose enough session context to build a safe attachment
- required files cannot be created or repaired without guessing hidden metadata

## Final Instruction

When using this skill:

- be conservative
- be schema-correct
- keep provenance visible
- attach the session, do not reinvent the system
