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
+-- docs
+-- providers
|   +-- hermes-router
+-- runtime
```

## Directory Meaning
- `contracts`
  - shared schemas and explicit contracts for the forest engine
- `docs`
  - product, architecture, and operating documents for OpenYggdrasil
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
    - provider-local code, policy, vault, and ops assets still live under this subtree
