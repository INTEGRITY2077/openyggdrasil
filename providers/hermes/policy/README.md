# Hermes Policy Boundary

This directory is a public policy pointer, not the full Hermes policy corpus.

## Public Role

- preserve a stable public path for safe Hermes policy summaries
- document which behavior is safe to depend on from the public repo
- avoid publishing internal policy trees, operator runbooks, raw sessions, or
  private workflow prompts

## Rule

Public code and public docs must not depend on gitignored local policy files.
If a policy concept is required for public understanding, summarize it in a
tracked public README or schema instead of linking to private material.
