# Providers

Providers are adapters that bind OpenYggdrasil to a specific runtime surface.

Provider directories should keep:
- ingress and egress adapters
- runtime-specific orchestration
- provider-specific bootstrap and hooks

Provider directories should not be the canonical home for:
- engine-level contracts
- provider-neutral runtime families
- canonical memory surfaces
- provider-neutral graph derivation stacks

Current provider:
- `hermes-router`

Planned provider-facing usage also includes skill-generated runtime attachments.

In that mode, provider folders act as placeholders and documentation anchors,
while live attachment artifacts are generated inside a workspace-local
`.yggdrasil/providers/...` tree.
