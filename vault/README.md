# OpenYggdrasil Vault

`vault/` is the **canonical provider-neutral memory surface** of OpenYggdrasil.

It is not the place where every provider dumps its entire raw session history.

## Core Rule

```text
provider raw stays near the provider
canonical promoted knowledge goes into the vault
```

## Why This Distinction Exists

If the vault becomes a catch-all session dump:

- provider-specific raw formats pollute the core
- session boundaries collapse
- provenance becomes harder to reason about
- the tracked repository becomes noisy and unsafe

So the vault must remain a **curated durable knowledge layer**, not a runtime
exhaust bucket.

## Two Surfaces Inside The Vault

The vault should be understood as having two different surfaces.

### 1. Deployment / tracked surface

This is the part that may be shipped, versioned, reviewed, and backed up as
canonical memory structure.

Examples:

- `concepts/`
- `entities/`
- `comparisons/`
- `queries/`
- `_meta/`
- `Home.md`
- `index.md`
- `log.md`
- `SCHEMA.md`

These are durable knowledge artifacts.

### 2. Local-only / ignored surface

This is the part that should remain runtime-local and normally gitignored.

Examples:

- Obsidian workspace state
- local caches
- transient staging files
- imported provider transcript snapshots
- runtime-only raw material that has not been promoted

These are not canonical memory pages.

## What Belongs In The Vault

The vault is for:

- canonical topic pages
- promoted durable answers
- curated comparisons
- provider-neutral concepts and entities
- append-only memory logs
- stable human/machine-readable knowledge pages

## What Does Not Belong In The Vault By Default

The vault should not directly become:

- a full provider session archive
- a live observer runtime surface
- a provider inbox tree
- a provider attachment tree
- a full transcript warehouse

Those belong either:

- in provider-owned raw locations
- in workspace-local `.yggdrasil/`
- in private raw archives outside the canonical vault

## Raw Policy

`vault/raw/` is allowed, but it must be interpreted narrowly.

It is for imported source material that supports canonical knowledge work, such
as:

- papers
- articles
- assets
- imported source notes

It is **not** the default home for all provider session transcripts.

Conversation/session raw should stay provider-side unless there is a deliberate
reason to snapshot or archive it.

## Provenance Policy

The preferred way to preserve provider raw is:

- symbolic reference through `source_ref`
- symbolic reference through `origin_locator`
- provider/session identifiers

Copying whole raw histories into the vault should be the exception, not the
default.

## Practical Rule For First-Time Distribution

When OpenYggdrasil is provided for first-time use:

- the vault ships as a **clean canonical skeleton**
- local runtime and local operator state stay ignored
- provider bootstrap creates workspace-local runtime surfaces elsewhere

This means the vault should be understandable and useful even before any
provider has attached.
