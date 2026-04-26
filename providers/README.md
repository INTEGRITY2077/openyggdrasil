# Providers

`providers/` contains public adapter boundaries for provider-specific runtime
surfaces.

Provider directories are not the canonical home for engine contracts,
provider-neutral runtime packages, vault memory, or Graphify derivation. Those
live at the repository root under `contracts/`, `runtime/`, `vault/`, and
`common/graphify/`.

## Current Public Provider Surfaces

| Provider | Public role |
| --- | --- |
| `hermes/` | Hermes adapter boundary, public manifest, and legacy harness compatibility surface. |
| `claude-code/` | Provider-native skill packaging target and clean-room attachment boundary. |
| `codex/` | Provider-neutral Codex attachment baseline and known degrade state. |
| `antigravity/` | Antigravity/Gemini-family bootstrap and generated-file packaging baseline. |

## Shared Rules

- Provider raw sessions and transcripts stay provider-side.
- Workspace-local attachment artifacts are generated under `.yggdrasil/`.
- Provider-specific private bundles, red-team material, and operator runbooks do
  not belong in the public repository.
- Provider directories may expose manifests, packaging baselines, compatibility
  shims, and public-safe README anchors.
