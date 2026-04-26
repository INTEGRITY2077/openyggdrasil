# Codex Provider

`providers/codex/` documents the Codex attachment baseline.

Codex currently attaches through the provider-neutral OpenYggdrasil skill and
shared workspace-local contracts. There is no provider-native installed package
target in the public deploy helper yet.

## Public Baseline

- generated workspace artifacts: `.yggdrasil/providers/codex/...`
- canonical instructions: `SKILL.md`
- attachment helpers: `runtime/attachments/`
- machine-readable baseline:
  `contracts/codex_provider_packaging_baseline.v1.schema.json`

## Required Contracts

- `provider_descriptor.v1`
- `session_attachment.v1`
- `inbox_binding.v1`
- `turn_delta.v1`

## Known Degrade State

- Codex has a provider-neutral attachment path.
- `runtime/attachments/deploy_skill.py` does not currently install a
  Codex-native provider file target.
- Raw Codex sessions and transcripts are not copied into OpenYggdrasil.
- The inbox is session-bound; no global inbox is allowed.
