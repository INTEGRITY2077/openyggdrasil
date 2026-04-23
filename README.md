# OpenYggdrasil

`OpenYggdrasil` is the umbrella workspace for the memory forest engine.

## Role
- `openyggdrasil` is the core memory/search structure
- `hermes-router` is a provider adapter under `providers/`
- `%HERMES_ROUTER_ROOT%` is the top-level ingress path that points to:
  - `%OPENYGGDRASIL_ROOT%\providers\hermes-router`
- `%OPENYGGDRASIL_COMPAT_ROOT%` remains only as a compatibility path that points to:
  - `%OPENYGGDRASIL_ROOT%`

## Workspace Layout
```text
%OPENYGGDRASIL_ROOT%
+-- contracts
+-- doc
+-- docs
+-- providers
|   +-- hermes-router
+-- runtime
```

## Directory Meaning
- `contracts`
  - shared schemas and explicit contracts for the forest engine
- `doc`
  - local-only centralized working documentation
  - intentionally gitignored
- `docs`
  - tracked public-facing product and architecture documents
- `providers`
  - runtime-specific adapters and routers
- `runtime`
  - core implementation space for engine roles and retrieval runtime

## Current Provider
- `hermes-router`
  - canonical path:
    - `%OPENYGGDRASIL_ROOT%\providers\hermes-router`
  - ingress path:
    - `%HERMES_ROUTER_ROOT%`
  - current active workspace:
    - provider-local code, vault layout, skills, and adapter runtime live under this subtree
  - local policy workspace:
    - `%OPENYGGDRASIL_ROOT%\doc\providers\hermes-router\policy`
