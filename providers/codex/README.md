# Codex Provider Placeholder

This directory is a placeholder only.

OpenYggdrasil does not require a pre-bundled static adapter here for the
skill-generated provider attachment flow.

When the OpenYggdrasil skill is used inside Codex, the active provider
attachment is expected to be generated inside the workspace-local:

- `.yggdrasil/providers/codex/...`

## Phase 6 Packaging Baseline

Codex is a typed degrade-ready provider baseline.

It attaches through the shared provider/session contracts, but it does not yet
have a provider-native deploy target in:

```text
runtime\attachments\deploy_skill.py
```

Activation path:

```text
Use the canonical OpenYggdrasil skill instructions in the current Codex
workspace and generate `.yggdrasil/providers/codex/...` through the shared
attachment contracts.
```

Contract baseline:

- provider descriptor: `provider_descriptor.v1`
- session attachment: `session_attachment.v1`
- inbox binding: `inbox_binding.v1`
- turn delta: `turn_delta.v1`
- machine-readable baseline: `codex_provider_packaging_baseline.v1`

Expected workspace-local tree:

```text
.yggdrasil/providers/codex/<provider_profile>/<session_component>/provider_descriptor.v1.json
.yggdrasil/providers/codex/<provider_profile>/<session_component>/session_attachment.v1.json
.yggdrasil/providers/codex/<provider_profile>/<session_component>/inbox_binding.v1.json
.yggdrasil/providers/codex/<provider_profile>/<session_component>/turn_delta.v1.jsonl
.yggdrasil/inbox/codex/<provider_profile>/<session_component>.jsonl
```

Known limitations:

- `deploy_skill.py` supports `claude-code`, `gemini`, `cursor`, and `windsurf`;
  it does not currently support a Codex provider-native file target.
- Codex attachment is currently provider-neutral and skill-generated, not an
  installed provider package.
- Provider raw sessions and transcripts are not copied into OpenYggdrasil.
- The inbox remains session-bound; no global inbox is allowed.
