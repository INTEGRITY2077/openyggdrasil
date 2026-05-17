# Contracts

`contracts/` is the public schema surface for openyggdrasil.

The runtime is intentionally contract-first. Modules pass typed JSON artifacts
instead of free-form prose whenever a result, handoff, lifecycle decision,
provider attachment, or unavailable state must cross a boundary.

The contract directory is audited as a refinery pipeline. A schema is a public
active pipe only when it has a producer or consumer and a runtime schema-file
validation/load path. A schema mentioned only as `schema_version` is a declared
interface, not a pressure-tested active pipe, until the refinery audit proves
the full flow.

## Contract Families

| Family | Example schemas | Boundary protected |
| --- | --- | --- |
| Provider attachment | `provider_descriptor.v1`, `session_attachment.v1`, `inbox_binding.v1`, `turn_delta.v1` | A provider/session must be explicit before it can attach to memory. |
| Capture and admission | `decision_surface.v1`, `decision_candidate.v1`, `session_structure_signal.v1`, `admission_verdict.v1` | Raw provider signals are normalized before evaluation. |
| Evaluation | `evaluator_verdict.v1`, `evaluator_amundsen_handoff.v1`, `promotion_worthiness.v1` | Weak or ambiguous candidates do not silently become memory. |
| Cultivation and lifecycle | `vault_record_lifecycle.v1`, `gardener_lifecycle_transition_request.v1`, `cross_provider_conflict_quarantine.v1`, `effort_aware_gardener_worthiness.v1` | Canonical records move through explicit active, stale, superseded, or quarantined states. |
| Retrieval | `pathfinder.v1`, `pathfinder_retrieval_result.v1`, `graphify_snapshot_manifest.v1`, `programmatic_tool_runtime_trace.v1`, `cross_provider_memory_consumption_result.v1` | Retrieval must preserve source refs, lifecycle state, freshness, provider boundary, and bounded tool-call traces. |
| Delivery | `postman_work_order.v1`, `worker_work_history.v1`, `worker_structured_receipt.v1`, `support_bundle.v1`, `inbox_packet.v1`, `mailbox_support_result.v1`, `mailbox_guard_result.v1`, `postman_delivery_handoff.v1` | Provider sessions receive bounded support, not raw vault dumps, and workers close mailbox work through typed receipts. |
| Reasoning | `reasoning_lease_request.v1`, `reasoning_lease_result.v1`, `provider_reasoning_gate.v1`, `module_effort_requirement.v1`, `module_effort_plan.v1`, `process_sandbox_runtime_decision.v1` | High-effort provider reasoning is optional, effort-aware, sandbox-policy gated, and typed when unavailable. |
| Provider packaging | `provider_descriptor.v1`, `provider_cold_start_healthcheck.v1`, `provider_runtime_integrity_result.v1` | Public adapters state what they can and cannot prove. |
| Capability lifecycle | `module_skill.v1`, `skill_metadata_reader.v1`, `programmatic_tool_runtime_trace.v1` | Skill, MCP, tool, and TST worker-manual source must be selected from repo-managed capability snapshots, not provider-local install state. |
| Runtime proof boundary | `thin_worker_chain_result.v1`, `role_split_integration_result.v1` | Runtime behavior is inspected through active result artifacts rather than hidden side effects. |

## Rules

- Schemas describe public engine boundaries, not private operator runbooks.
- A schema may represent unavailable or declined capability; it must not hide
  that state behind a generic failure.
- Provider raw sessions, raw transcripts, credentials, and private development
  history do not belong in contract examples.
- Provider-local SKILL/MCP files are projection/install artifacts. Capability
  lifecycle contracts must point back to repo-managed source and deployment
  receipts before an install is considered managed.
- New runtime modules should add or reuse a schema before introducing a new
  cross-module artifact.
- Schemas with no producer, validator, consumer, or manifest compatibility
  reason do not remain public active contracts. Move them to private quarantine
  or a legacy/private-only area until a flow map proves circulation.

## Verification

The public import smoke exercises the schema/runtime import surface:

```powershell
py -3 runtime/import_smoke.py
```

The refinery audit checks whether public contracts actually circulate:

```powershell
py -3 scripts/contract_refinery_audit.py --out contracts/refinery_audit.current.json
```
