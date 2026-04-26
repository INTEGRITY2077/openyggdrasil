# Vault Schema

This file defines what the public OpenYggdrasil vault is allowed to contain.

The vault is a canonical promoted memory layer, not a generic runtime dump.

## Domain

The vault stores provider-neutral durable knowledge such as:

- concepts
- entities
- comparisons
- promoted query answers
- curated summaries
- provenance-backed public notes

## Folder Meaning

### `concepts/`

Technical ideas, patterns, principles, and recurring themes.

### `entities/`

People, organizations, products, models, systems, labs, or projects.

### `comparisons/`

Side-by-side analyses or decision-facing comparisons.

### `queries/`

High-value answers worth preserving because they would be expensive to
reconstruct.

### `_meta/`

Operational notes, templates, maps, and vault governance files.

### `raw/`

Imported supporting source material. This folder may exist locally, but it is
not the default destination for provider transcripts.

## Local-Only Material

Treat these as ignored or external to the public vault unless explicitly
promoted:

- Obsidian workspace state
- caches
- transient imports
- staging scratch
- provider transcript dumps
- runtime session exhaust

## Page Conventions

- file names: lowercase, hyphens, no spaces
- every durable page should be concise and reviewable
- index and log should reflect meaningful public additions
- canonical pages should be update-or-create, not duplicated by prompt wording

## Frontmatter Baseline

```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from taxonomy]
sources: [symbolic references or public source paths]
---
```

## Filing Rule

Promote into the vault only when the result is:

- durable
- non-trivial
- hard to re-derive
- reusable across future sessions
- safe to publish

Do not file:

- trivial replies
- incidental mentions
- temporary operator chatter
- raw turn-by-turn session exhaust
- private development history

## Summary

```text
vault = canonical promoted memory
not = full provider session warehouse
```
