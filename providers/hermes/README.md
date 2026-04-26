# Hermes

`hermes` is the Hermes-specific provider adapter under `OpenYggdrasil`.

## Role
- binds Hermes session ingress to the OpenYggdrasil memory/search structure
- owns the current Hermes-facing runtime surface
- remains reachable through:
  - `%HERMES_ROOT%`

## Current Shape
- this subtree is still the active provider workspace
- provider-local assets currently live here:
  - `projects`
  - `policy` (public pointer only)
  - `skills`
  - `memories`
  - `hooks`
- local-only provider documentation is centralized at:
  - `%OPENYGGDRASIL_ROOT%\doc\providers\hermes\policy`
- runtime `ops` artifacts remain provider-local at execution time but are not tracked in git
- core runtime, contracts, canonical vault, and Graphify derivation now live at the OpenYggdrasil root

## Canonical Paths
- provider workspace:
  - `%OPENYGGDRASIL_ROOT%\providers\hermes`
- Hermes ingress:
  - `%HERMES_ROOT%`
- local policy documentation:
  - `%OPENYGGDRASIL_ROOT%\doc\providers\hermes\policy`
- core runtime:
  - `%OPENYGGDRASIL_ROOT%\runtime`
- canonical vault:
  - `%OPENYGGDRASIL_ROOT%\vault`
- Hermes graphify project:
  - `%OPENYGGDRASIL_ROOT%\providers\hermes\projects\graphify-poc`

## Phase 6 Packaging Baseline

Hermes is the strongest Phase 6 provider baseline, but its live foreground
surface is still typed unavailable. Treat the profile skill and workspace-local
attachment contracts as the deployable baseline, not as a live foreground proof.

Install path:

```text
~/.hermes/profiles/<provider_profile>/skills/autonomous-ai-agents/openyggdrasil-foreground-probe/SKILL.md
```

Default activation:

```text
Hermes profile skill `openyggdrasil-foreground-probe`
```

Repo-owned sync surface:

```text
runtime\attachments\deploy_hermes_profile_skill.py
```

Contract baseline:

- provider descriptor: `provider_descriptor.v1`
- session attachment: `session_attachment.v1`
- inbox binding: `inbox_binding.v1`
- turn delta: `turn_delta.v1`
- live foreground limitation: `hermes_foreground_unavailable_contract.v1`
- machine-readable baseline: `hermes_provider_packaging_baseline.v1`

Expected workspace-local tree:

```text
.yggdrasil/providers/hermes/<provider_profile>/<session_component>/provider_descriptor.v1.json
.yggdrasil/providers/hermes/<provider_profile>/<session_component>/session_attachment.v1.json
.yggdrasil/providers/hermes/<provider_profile>/<session_component>/inbox_binding.v1.json
.yggdrasil/providers/hermes/<provider_profile>/<session_component>/turn_delta.v1.jsonl
.yggdrasil/inbox/hermes/<provider_profile>/<session_component>.jsonl
```

Known limitations:

- `providers\hermes\projects\harness\hermes_foreground_probe.py` is absent, so
  Phase 6 records live foreground as typed unavailable.
- Foreground-equivalent bootstrap and memory roundtrip proofs must not be
  relabeled as live foreground proof.
- Provider raw sessions and transcripts are not copied into OpenYggdrasil.
- The inbox remains session-bound; no global inbox is allowed.
