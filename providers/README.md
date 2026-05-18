# Providers

`providers/` contains public adapter boundaries for provider-specific runtime
surfaces.

Provider directories are not the canonical home for engine contracts,
provider-neutral runtime packages, vault memory, or Graphify derivation. Those
live at the repository root under `contracts/`, `runtime/`, `vault/`, and
`common/graphify/`.

Provider directories are also not the source of truth for Skill, MCP, tool, or
TST worker-manual lifecycle management. That source/control plane is planned
under `capabilities/`. Provider-local skill and MCP files are projection or
install artifacts derived from capability snapshots and must be backed by
deployment receipts before they are considered managed.

## Current Public Provider Surfaces

| Provider | Public role |
| --- | --- |
| `hermes/` | Hermes adapter boundary, public manifest, and legacy harness compatibility surface. |
| `claude-code/` | Provider-native skill packaging target and independent attachment boundary. |
| `codex/` | Provider-neutral Codex attachment baseline and known degrade state. |
| `antigravity/` | Antigravity/Gemini-family bootstrap and generated-file packaging baseline. |

## Shared Rules

- Provider raw sessions and transcripts stay provider-side.
- Workspace-local attachment artifacts are generated under `.yggdrasil/`.
- Provider-specific private bundles, red-team material, and operator runbooks do
  not belong in the public repository.
- Provider directories may expose manifests, packaging baselines, compatibility
  shims, and public-safe README anchors.
- Provider-installed SKILL/MCP state must not be promoted as product truth
  unless the repo capability source, projection, install receipt, and drift
  check agree.
