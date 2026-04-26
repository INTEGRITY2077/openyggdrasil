---
title: Why should the external harness own transcript promotion and Graphify rebuild instead of Hermes core?
created: 2026-04-21
updated: 2026-04-26
type: query
tags: [query, harness, graphify, public-example]
sources: [providers/hermes/projects/harness/README.md, common/graphify/README.md]
---

# Why should the external harness own transcript promotion and Graphify rebuild instead of Hermes core?

## Question

Why should the external harness own transcript promotion and Graphify rebuild
instead of Hermes core?

## Answer

Promotion and graph rebuild are boundary-management tasks that need source
policy, lifecycle review, and publication rules. Keeping them outside provider
core preserves a smaller provider runtime while OpenYggdrasil migrates durable
behavior into root contracts, runtime modules, and Graphify support surfaces.

## Related

- [[concepts/memory-architecture]]
- [[concepts/llm-wiki-pattern]]
