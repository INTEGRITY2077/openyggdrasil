# Vault Schema

## Purpose

This file defines what the OpenYggdrasil vault is allowed to contain.

The vault is a **canonical memory layer**, not a generic runtime dump.

## Domain

The vault stores provider-neutral durable knowledge such as:

- concepts
- entities
- comparisons
- promoted queries
- curated summaries
- provenance-backed durable notes

## Folder Meaning

### `concepts/`

Technical ideas, patterns, principles, and recurring themes.

### `entities/`

People, organizations, products, models, systems, labs, projects.

### `comparisons/`

Side-by-side analyses or decision-facing comparisons.

### `queries/`

High-value answers worth preserving because they would be expensive to
reconstruct.

### `_meta/`

Operational notes, templates, maps, and vault governance files.

### `raw/`

Imported supporting source material.

This may include:

- papers
- articles
- assets

It should **not** be treated as the default destination for full provider
session transcript capture.

## Deployment Surface

Tracked canonical memory should stay readable and reviewable.

Expected tracked content:

- folder structure
- canonical markdown pages
- `index.md`
- `log.md`
- schema and governance docs

## Local-Only Surface

The following should be treated as local-only or gitignored:

- Obsidian workspace state
- caches
- transient imports
- staging scratch
- provider transcript dumps
- runtime session exhaust

## Session Raw Rule

Provider session raw belongs primarily to the provider side.

OpenYggdrasil should prefer:

- `source_ref`
- `origin_locator`
- `provider_id`
- `provider_profile`
- `provider_session_id`
- `session_uid`

to point back to provider raw.

Only copy provider raw into a vault-local archive when there is a deliberate
need such as:

- audit
- forensic recovery
- durable offline preservation

## Page Conventions

- file names: lowercase, hyphens, no spaces
- every durable page should be concise and reviewable
- index and log should reflect meaningful additions
- canonical pages should be update-or-create, not duplicated by prompt wording

## Frontmatter Baseline

```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from taxonomy]
sources: [symbolic references or imported source paths]
---
```

## Filing Rule

Promote into the vault only when the result is:

- durable
- non-trivial
- hard to re-derive
- reusable across future sessions

Do not file:

- trivial replies
- incidental mentions
- temporary operator chatter
- raw turn-by-turn session exhaust

## Summary

```text
vault = canonical promoted memory
not = full provider session warehouse
```
