# Hermes Harness

This directory is a legacy Hermes-facing harness compatibility surface.

It contains older adapter code for mailbox, worker, promotion, graph rebuild,
answer-support, and orchestration experiments. The current public architecture
keeps canonical engine responsibilities at the root:

- contracts: `contracts/`
- provider-neutral runtime: `runtime/`
- canonical memory: `vault/`
- Graphify support: `common/graphify/`

## Current Role

The harness may still be useful for compatibility review and migration, but it
is not the primary place to add new provider-neutral behavior.

New public work should prefer:

- attachment and provider packaging helpers under `runtime/attachments/`
- mailbox and support delivery under `runtime/delivery/`
- Pathfinder and Graphify support under `runtime/retrieval/`
- reasoning lease and availability gates under `runtime/reasoning/`
- runner proof entrypoints under `runtime/runner/`

## Runtime Artifacts

Harness runtime artifacts such as queues, locks, mailbox state, plugin logs,
and replay output must remain generated/local and must not be committed.

## Safety Boundary

- Do not copy raw Hermes sessions or transcripts into this directory.
- Do not add credential helpers or private operator workflows here.
- Do not revive observer-daemon semantic ownership from this legacy surface.
- Treat successful harness behavior as evidence for migration into root runtime
  contracts, not as permission to bypass those contracts.
