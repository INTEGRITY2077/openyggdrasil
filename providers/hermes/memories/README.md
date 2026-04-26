# Hermes Memories Boundary

This directory is a public documentation anchor for Hermes provider memory
files.

Provider-native memory files are not the OpenYggdrasil source of truth. Durable
provider-neutral memory belongs in the root `vault/` only after promotion and
provenance review.

## Rule

- Keep Hermes raw/provider memory near Hermes.
- Reference provider memory through source refs or origin locators when needed.
- Promote only durable, provider-neutral knowledge into `vault/`.
