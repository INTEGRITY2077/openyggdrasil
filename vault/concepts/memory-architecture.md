---
title: Memory Architecture
created: 2026-04-19
updated: 2026-04-19
type: concept
tags: [memory, retrieval, agent]
sources: []
---

# Memory Architecture

This setup uses three complementary layers:

1. Hermes durable memory for compact stable facts
2. Session recall for past conversation context
3. This vault as long-form external knowledge memory

## Design principle
Keep short user/environment facts in Hermes memory, but keep accumulated research and synthesized knowledge in the wiki vault.

## Related
- [[concepts/llm-wiki-pattern]]
- [[Home]]
- [[README]]
