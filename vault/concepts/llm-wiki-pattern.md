---
title: LLM Wiki Pattern
created: 2026-04-19
updated: 2026-04-26
type: concept
tags: [memory, retrieval, tooling]
sources: []
---

# LLM Wiki Pattern

The LLM Wiki pattern stores accumulated knowledge as maintained Markdown pages
instead of rediscovering facts from scratch on every query.

## Why It Matters

- Knowledge compounds across sessions.
- Humans and tools can inspect the same memory.
- Summaries can link back to source refs and provenance.
- Retrieval can prefer curated pages before falling back to raw material.

## OpenYggdrasil Interpretation

OpenYggdrasil uses the wiki pattern as one layer of memory, but adds stricter
runtime boundaries:

- contracts define cross-module artifacts;
- lifecycle state marks active, stale, or superseded memory;
- Graphify output is derived support, not SOT;
- provider raw sessions are referenced symbolically instead of copied by
  default.

## Related

- [[concepts/memory-architecture]]
- [[_meta/intake-workflow]]
- [[Home]]
