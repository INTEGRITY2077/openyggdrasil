---
title: What does automatic session discovery do in the external harness?
created: 2026-04-21
updated: 2026-04-26
type: query
tags: [query, harness, public-example]
sources: [providers/hermes/projects/harness/README.md]
---

# What does automatic session discovery do in the external harness?

## Question

What does automatic session discovery do in the external harness?

## Answer

Automatic session discovery looks for provider sessions that can be considered
for bounded processing without manually naming each session. In the current
public architecture, that behavior belongs to legacy harness compatibility or a
future root runtime migration, not to canonical vault writes by itself.

## Related

- [[concepts/memory-architecture]]
