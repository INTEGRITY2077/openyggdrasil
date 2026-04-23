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
