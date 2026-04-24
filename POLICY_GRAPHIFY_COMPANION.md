# Graphify Companion Distribution Policy

## Purpose

This document fixes the public distribution policy for the current OpenYggdrasil stack
while the graph query layer remains external.

The active rule is:

- OpenYggdrasil core remains provider-neutral and authoritative for contracts, runtime, and vault storage
- Graphify is distributed as a default-installed companion layer
- Graphify must not become a hard runtime dependency that can take down core memory operations

Short rule:

```text
default-installed companion
not authoritative core
not required for core survival
```

## Current Position

OpenYggdrasil uses Graphify as a derived query layer over the canonical vault.

That means:

- `vault/` remains the source of truth
- Graphify remains a derived query surface
- direct note reads, provenance reads, and pathfinder bundles remain valid fallback paths

Graphify is useful enough for distribution consistency that it should be installed by default.
It is not authoritative enough to become the only surviving query path.

## Distribution Model

### Default install

The default public distribution should install:

1. OpenYggdrasil core
2. Graphify companion

This is the recommended default because it gives operators one reproducible install path and
keeps the graph query layer available out of the box.

### Minimal install

A reduced `core-only` mode is still allowed for:

- recovery
- constrained environments
- debugging
- environments where the graph companion cannot be installed safely

`core-only` is a supported fallback mode, not the primary distribution mode.

## Boundary Rule

Graphify must be treated as:

- a derived graph/query layer
- a companion dependency
- a replaceable external engine

Graphify must not be treated as:

- the OpenYggdrasil source of truth
- the owner of canonical memory
- the owner of provider attachment policy
- the owner of provider bootstrap or hook installation

OpenYggdrasil owns:

- contracts
- provider attachment rules
- runtime fallback policy
- canonical vault writes
- provider-facing bootstrap behavior

Graphify owns only:

- graph derivation
- graph query execution
- graph-oriented explain/path/query behavior

## Installation Rules

### 1. Install the engine, not the product surface

OpenYggdrasil distributions should install the Graphify engine surface needed for query/rebuild use.

OpenYggdrasil distributions should not rely on upstream product-side install behavior such as:

- `graphify install`
- upstream AGENTS.md mutation
- upstream hook installation
- upstream provider-specific bootstrap side effects

Those surfaces belong to the upstream Graphify product and should not define the OpenYggdrasil runtime.

### 2. OpenYggdrasil manages bootstrap

OpenYggdrasil must manage its own:

- skills
- bootstrap instructions
- hooks
- provider-facing configuration
- runtime entrypoints

### 3. Use pinned companion versions

The Graphify companion must be installed through an OpenYggdrasil-managed pinned version path.

This means:

- exact package version must be pinned
- exact lockfile or equivalent reproducibility control must exist
- companion upgrades must be deliberate

## Runtime Rules

### 1. Preferred path when healthy

When the graph layer is present and fresh, OpenYggdrasil should prefer:

- Graphify `query`
- Graphify `path`
- Graphify `explain`

for structural and relationship-heavy retrieval.

### 2. Mandatory fallback when unhealthy

If Graphify is:

- missing
- stale
- broken
- unavailable in the current runtime

OpenYggdrasil must fall back to:

1. direct canonical note reads
2. provenance-backed topic/episode retrieval
3. raw/session reads only as last fallback

### 3. Core survival rule

Graphify failure must not block:

- promotion into `vault/`
- canonical note updates
- provenance persistence
- attachment/runtime control surfaces
- provider session operation

The graph layer may degrade query quality.
It must not destroy the underlying memory system.

## Network and Privacy Rule

Because Graphify can involve external surfaces, the default OpenYggdrasil distribution must treat these as companion-layer concerns:

- semantic extraction may depend on the current provider model API
- URL ingest is networked and must remain explicit or opt-in
- HTML visualization may rely on upstream CDN behavior unless localized later

These surfaces must not be silently redefined as OpenYggdrasil core behavior.

## Licensing Rule

The public repository and public distribution must carry a third-party notice for Graphify.

At minimum:

- upstream project identity
- upstream repository URL
- upstream license type
- required copyright and license notice

Transitive dependency licensing is a separate review surface and must not be implicitly treated as fully covered by the direct Graphify notice.

## Future Direction

This policy is intentionally transitional.

The long-term options remain:

1. continue with default-installed companion distribution
2. vendor the graph engine into the repository
3. fully replace the external engine with a native OpenYggdrasil graph layer

Until one of those transitions is completed, the active policy is:

```text
ship Graphify by default
keep OpenYggdrasil core alive without it
do not let upstream product install surfaces own our runtime
```
