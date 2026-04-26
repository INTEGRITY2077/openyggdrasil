# Runtime Reasoning

`runtime/reasoning/` owns optional Reasoning Lease contracts and provider
capability gates.

Reasoning Lease is not the base pipeline. It is a typed boundary for work that
needs provider-owned or high-effort reasoning beyond deterministic runtime
checks.

## Responsibilities

- build and validate `reasoning_lease_request.v1` and
  `reasoning_lease_result.v1`
- normalize provider effort vocabulary
- declare module effort requirements and effort plans
- expose provider reasoning capability gates
- enforce resource and sandbox boundaries
- return typed unavailable, declined, timeout, blocked, or unknown-effort
  results when a provider cannot safely execute the lease

## Current Policy

- Deterministic modules must keep working without a lease.
- Distiller and Evaluator are high-effort planning surfaces.
- Amundsen and Pathfinder are medium-effort planning surfaces.
- Provider-side resource requests must not ask the user for API keys, OAuth, or
  stored credentials.
- Hermes background reasoning remains typed unless live result completion is
  explicitly proven.
