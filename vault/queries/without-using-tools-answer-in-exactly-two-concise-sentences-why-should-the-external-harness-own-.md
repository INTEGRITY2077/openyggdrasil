---
title: Without using tools, answer in exactly two concise sentences: Why should the external harness own transcript promotion and Graphify rebuild instead of Hermes core?
created: 2026-04-21
updated: 2026-04-21
type: query
tags: [query, hermes, transcript-promotion]
sources: [raw/transcripts/2026/2026-04-21-20260421_191840_0a17f8.md]
---

# Without using tools, answer in exactly two concise sentences: Why should the external harness own transcript promotion and Graphify rebuild instead of Hermes core?

## Question

Without using tools, answer in exactly two concise sentences: Why should the external harness own transcript promotion and Graphify rebuild instead of Hermes core?

## Answer

Because transcript promotion and Graphify rebuild are boundary-management tasks that belong to the outer orchestration layer, which has the right visibility into session lifecycle, approvals, and publication policy. Keeping them out of Hermes core preserves a smaller, more stable runtime while letting the harness evolve ingestion and rebuild workflows independently.

## Related

- raw source: `raw/transcripts/2026/2026-04-21-20260421_191840_0a17f8.md`
- session_id: `20260421_191840_0a17f8`
- profile: `graph`
