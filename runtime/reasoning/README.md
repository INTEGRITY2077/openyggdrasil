# Runtime Reasoning

This package owns optional high-reasoning lease contracts.

`Reasoning Lease` is not a pipeline stage and is not required for the base chain.
It is a cross-cutting service boundary for future provider-owned headless workers,
local workers, or manual review.

Default policy:
- If `provider_descriptor.capabilities.background_reasoning_descriptor` is present, `background_reasoning=true` only means completed support when the descriptor is `support_status=supported`, `completion_status=live_proven`, and `live_proof_required=false`.
- Hermes `/background` starts as `support_status=adapted_candidate` with `live_proof_required=true`; it must keep the deterministic base path until later Phase 4 proof points close.
- `hermes_background_invocation_smoke.v1` can prove only the explicit `/background` command/gateway invocation surface from static provider reference markers. It does not claim a live task result or completed reasoning lease.
- `hermes_background_task_capture.v1` can capture a `bg_` task reference from explicit gateway output while retaining only the task reference and output digest, never provider raw output or raw session content. It does not claim lease completion or result ingestion.
- `hermes_background_result_contract.v1` wraps a Hermes background result into `reasoning_lease_result.v1` only after an explicit result gate returns `allowed`, source and worker refs are present, and effort metadata is verified or accepted. Blocked, unavailable, unknown-effort, or unsafe surfaces remain typed non-completed results.
- `hermes_background_unavailable_contract.v1` emits runner-visible non-completed results for unsupported provider, provider decline, timeout, cancel, no visible result, handoff gate blocked/unavailable, effort below minimum, effort unknown/unverifiable, and sandbox/security unavailable states.
- `hermes_state_metadata_policy.v1` allows provider state paths such as `state.db` only as metadata/source-ref/provenance hints. It rejects provider state as result text and requires typed gateway/result surfaces, digests, refs, or explicit unavailable state for verification.
- `hermes_main_context_non_accumulation.v1` records static or live evidence that worker prompts, traces, raw tool outputs, and lease result payloads are not appended to the provider main foreground conversation. If evidence is insufficient, it emits typed unavailable; if raw material or foreground append is attempted, it emits a blocked unsafe surface.
- If background reasoning is missing, unavailable, or only an adapted candidate, the caller must keep the deterministic base path or mark manual review.
- Current core modules must not depend on a lease to keep `decision_surface -> decision_candidate` working.
- Provider-side resource requests must not ask the user for API keys or OAuth. They either produce a provider-headless lease request, an explicit decline result, or a fallback result.
