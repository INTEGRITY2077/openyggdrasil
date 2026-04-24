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
- core graphify project:
  - `%OPENYGGDRASIL_ROOT%\projects\graphify-poc`
