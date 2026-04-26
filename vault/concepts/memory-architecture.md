---
title: Memory Architecture
created: 2026-04-19
updated: 2026-04-26
type: concept
tags: [memory, retrieval, agent]
sources: []
---

# Memory Architecture

OpenYggdrasil separates memory into explicit layers so provider tools do not
collapse runtime state, raw sessions, and canonical knowledge into one bucket.

## Layers

1. Provider raw material stays near the provider.
2. Workspace-local runtime state lives under `.yggdrasil/`.
3. Canonical promoted memory lives in `vault/`.
4. Derived graph/wiki/index support lives under `common/graphify/` outputs.
5. Delivery to a provider session happens through bounded support bundles and
   session-bound inbox packets.

## Design Principle

Canonical memory should be source-ref backed, lifecycle-aware, and safe to
inspect. Derived support can help retrieval, but it must not replace source of
truth.

## Related

- [[concepts/llm-wiki-pattern]]
- [[Home]]
- [[README]]
