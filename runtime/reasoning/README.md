# Runtime Reasoning

This package owns optional high-reasoning lease contracts.

`Reasoning Lease` is not a pipeline stage and is not required for the base chain.
It is a cross-cutting service boundary for future provider-owned headless workers,
local workers, or manual review.

Default policy:
- If `provider_descriptor.capabilities.background_reasoning_descriptor` is present, `background_reasoning=true` only means completed support when the descriptor is `support_status=supported`, `completion_status=live_proven`, and `live_proof_required=false`.
- Hermes `/background` starts as `support_status=adapted_candidate` with `live_proof_required=true`; it must keep the deterministic base path until later Phase 4 proof points close.
- `hermes_background_invocation_smoke.v1` can prove only the explicit `/background` command/gateway invocation surface from static provider reference markers. It does not claim a live task result or completed reasoning lease.
- If background reasoning is missing, unavailable, or only an adapted candidate, the caller must keep the deterministic base path or mark manual review.
- Current core modules must not depend on a lease to keep `decision_surface -> decision_candidate` working.
- Provider-side resource requests must not ask the user for API keys or OAuth. They either produce a provider-headless lease request, an explicit decline result, or a fallback result.
