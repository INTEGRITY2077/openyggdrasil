---
title: Read SCHEMA.md, index.md, and recent log.md from the canonical wiki.
created: 2026-04-21
updated: 2026-04-21
type: query
tags: [query, hermes, transcript-promotion]
sources: [raw/transcripts/2026/2026-04-21-20260421_145614_f092cc.md]
---

# Read SCHEMA.md, index.md, and recent log.md from the canonical wiki.

## Question

Read SCHEMA.md, index.md, and recent log.md from the canonical wiki.
Do not modify files.
Describe the llm-wiki response contract using this exact structure:
Decision
Schema Table
Why
Now
Later

## Answer

Decision

The llm-wiki response contract is a 5-part, schema-friendly answer format: one-line conclusion, compact metadata table, short reasons, immediate state/actions, and deferred follow-up.

Schema Table

| field | value |
|---|---|
| response_type | structure |
| promotion_target | none |
| confidence | high |
| sources | [[SCHEMA]], `index.md`, `log.md`, `research/llm-wiki` skill |
| now | Use the fixed order: `Decision`, `Schema Table`, `Why`, `Now`, `Later` |
| later | Promote valuable answers into `queries/`, `concepts/`, `entities/`, or `comparisons/` when filing threshold is met |

Why

- The skill explicitly defines the default response shape as:
  1. `Decision`
  2. `Schema Table`
  3. `Why`
  4. `Now`
  5. `Later`
- The purpose is to make wiki answers easy to parse, easy to promote into pages, and cheap to reinterpret later.
- `SCHEMA.md` reinforces this by defining a query workflow and a filing threshold for preserving substantial answers.
- `index.md` shows this canonical vault is still sparse, so a strict contract helps future growth stay consistent.
- `log.md` shows only the vault initialization so far, meaning the contract is part of the intended operating model rather than a later patch.

Now

- Canonical wiki path used: `/mnt/d/Hermes/central/vault`
- Read without modification:
  - `/mnt/d/Hermes/central/vault/SCHEMA.md`
  - `/mnt/d/Hermes/central/vault/index.md`
  - `/mnt/d/Hermes/central/vault/log.md`
- Current contract, in plain terms:
  - `Decision`: one sentence
  - `Schema Table`: compact metadata table
  - `Why`: 2–5 short bullets
  - `Now`: immediate action or current state
  - `Later`: deferred or optional follow-up

Later

- As the vault grows, the same contract can be reused for query, promotion, filing, lint, ingest, and structure responses.
- If the user wants, this contract can later be mirrored into a dedicated wiki page or query page, but I did not modify any files here.

## Related

- raw source: `raw/transcripts/2026/2026-04-21-20260421_145614_f092cc.md`
- session_id: `20260421_145614_f092cc`
