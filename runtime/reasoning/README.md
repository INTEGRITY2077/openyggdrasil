# Runtime Reasoning

This package owns optional high-reasoning lease contracts.

`Reasoning Lease` is not a pipeline stage and is not required for the base chain.
It is a cross-cutting service boundary for future provider-owned headless workers,
local workers, or manual review.

Default policy:
- If `provider_descriptor.capabilities.background_reasoning` is `true`, a caller may submit a lease request.
- If it is missing or `false`, the caller must keep the deterministic base path or mark manual review.
- Current core modules must not depend on a lease to keep `decision_surface -> decision_candidate` working.
