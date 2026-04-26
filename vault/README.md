# OpenYggdrasil Vault

`vault/` is the canonical provider-neutral memory surface for public
OpenYggdrasil knowledge.

It is not a place for every provider to dump raw session history.

## Core Rule

```text
provider raw stays near the provider
canonical promoted knowledge goes into the vault
```

## What Belongs Here

- durable concepts and architecture notes
- reusable query answers
- curated comparisons
- public-safe provenance references
- schema and governance docs
- append-only public memory log entries

## What Does Not Belong Here By Default

- full provider sessions or transcripts
- live provider inboxes
- workspace-local `.yggdrasil/` artifacts
- runtime caches or queues
- private development history
- credential, OAuth, or operator runbook material

## Vault Surfaces

### Tracked Public Surface

Tracked vault pages should be concise, reviewable, and safe to publish.

Examples:

- `concepts/`
- `queries/`
- `_meta/`
- `Home.md`
- `index.md`
- `log.md`
- `SCHEMA.md`

### Local-Only Surface

Local vault scratch material, imported raw sources, Obsidian state, caches, and
unpromoted provider material should remain ignored or outside the public repo.

## Provenance Policy

Prefer symbolic references:

- `source_ref`
- `origin_locator`
- `provider_id`
- `provider_profile`
- `provider_session_id`
- `session_uid`

Copying whole raw provider histories into the public vault should be treated as
an exception that requires an explicit public-safe reason.
