---
title: Intake Workflow
created: 2026-04-19
updated: 2026-04-19
type: summary
tags: [tooling, memory]
sources: []
---

# Intake Workflow

1. Save source material under `raw/articles/`, `raw/papers/`, or `raw/transcripts/`
2. Ask Hermes to ingest the source into the vault
3. Hermes should:
   - read [[SCHEMA]]
   - check [[index]]
   - scan recent entries in `log.md`
   - create or update relevant pages
   - add backlinks and update `index.md`
   - append a `log.md` entry

Related: [[concepts/llm-wiki-pattern]], [[concepts/memory-architecture]]
