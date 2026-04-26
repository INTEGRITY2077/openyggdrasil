# Contracts

`contracts/` is the public schema surface for OpenYggdrasil.

The runtime is intentionally contract-first. Modules pass typed JSON artifacts
instead of free-form prose whenever a result, handoff, lifecycle decision,
provider attachment, or unavailable state must cross a boundary.

## Contract Families

| Family | Example schemas | Boundary protected |
| --- | --- | --- |
| Provider attachment | `provider_descriptor.v1`, `session_attachment.v1`, `inbox_binding.v1`, `turn_delta.v1` | A provider/session must be explicit before it can attach to memory. |
| Capture and admission | `decision_surface.v1`, `decision_candidate.v1`, `session_structure_signal.v1`, `admission_verdict.v1` | Raw provider signals are normalized before evaluation. |
| Evaluation | `evaluator_verdict.v1`, `evaluator_amundsen_handoff.v1`, `promotion_worthiness.v1`, `chain_health_scorecard.v1` | Weak or ambiguous candidates do not silently become memory. |
| Cultivation and lifecycle | `vault_record_lifecycle.v1`, `gardener_lifecycle_transition_request.v1`, `cross_provider_conflict_quarantine.v1`, `effort_aware_gardener_worthiness.v1` | Canonical records move through explicit active, stale, superseded, or quarantined states. |
| Retrieval | `pathfinder.v1`, `pathfinder_retrieval_result.v1`, `graphify_snapshot_manifest.v1`, `cross_provider_memory_consumption_result.v1` | Retrieval must preserve source refs, lifecycle state, freshness, and provider boundary. |
| Delivery | `support_bundle.v1`, `inbox_packet.v1`, `mailbox_support_result.v1`, `mailbox_guard_result.v1`, `postman_delivery_handoff.v1` | Provider sessions receive bounded support, not raw vault dumps. |
| Reasoning | `reasoning_lease_request.v1`, `reasoning_lease_result.v1`, `provider_reasoning_gate.v1`, `module_effort_requirement.v1`, `module_effort_plan.v1` | High-effort provider reasoning is optional, effort-aware, and typed when unavailable. |
| Provider packaging | `hermes_provider_packaging_baseline.v1`, `claude_code_provider_packaging_baseline.v1`, `codex_provider_packaging_baseline.v1`, `antigravity_provider_packaging_baseline.v1`, `provider_packaging_known_limitations_matrix.v1` | Public adapters state what they can and cannot prove. |
| Runner proof | `thin_worker_chain_result.v1`, `failure_fallback_regression_result.v1`, `real_ux_regression_result.v1`, `provider_declined_runner_visibility.v1` | Chain behavior is inspected through result artifacts rather than hidden side effects. |

## Rules

- Schemas describe public engine boundaries, not private operator runbooks.
- A schema may represent unavailable or declined capability; it must not hide
  that state behind a generic failure.
- Provider raw sessions, raw transcripts, credentials, and private development
  history do not belong in contract examples.
- New runtime modules should add or reuse a schema before introducing a new
  cross-module artifact.

## Verification

The public import smoke exercises the schema/runtime import surface:

```powershell
py -3 runtime/import_smoke.py
```
