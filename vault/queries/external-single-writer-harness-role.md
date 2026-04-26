---
title: What is the role of an external single-writer harness in the Hermes architecture?
created: 2026-04-21
updated: 2026-04-26
type: query
tags: [query, harness, public-example]
sources: [providers/hermes/projects/harness/README.md]
---

# What is the role of an external single-writer harness in the Hermes architecture?

## Question

What is the role of an external single-writer harness in the Hermes
architecture?

## Answer

The single-writer harness serialized older Hermes-facing queue, mailbox,
promotion, and graph rebuild experiments so concurrent tools would not corrupt
shared state. In the current public architecture, that lesson is preserved as a
contract boundary: new provider-neutral behavior should migrate into root
runtime modules and typed schemas instead of bypassing them.

## Related

- [[concepts/memory-architecture]]
- [[queries/without-using-tools-answer-in-exactly-two-concise-sentences-why-should-the-external-harness-own-]]
