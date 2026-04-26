from __future__ import annotations

import importlib
from dataclasses import dataclass


CANONICAL_RUNTIME_MODULES = [
    "admission.admission_stub",
    "admission.amundsen_stub",
    "admission.amundsen_nursery_handoff",
    "admission.decision_contracts",
    "admission.session_admission_gate",
    "attachments.antigravity_provider_packaging_baseline",
    "attachments.bootstrap_contract",
    "attachments.claude_code_provider_packaging_baseline",
    "attachments.codex_provider_packaging_baseline",
    "attachments.hermes_foreground_unavailable_contract",
    "attachments.hermes_provider_packaging_baseline",
    "attachments.provider_attachment",
    "attachments.provider_inbox",
    "attachments.provider_packaging_known_limitations_matrix",
    "attachments.provider_tooling_classification",
    "capture.decision_distiller",
    "capture.provider_runtime_integrity",
    "capture.session_structure_signal",
    "common.jsonl_io",
    "common.map_identity",
    "common.wsl_runner",
    "cultivation.cross_provider_conflict_quarantine",
    "cultivation.effort_aware_gardener_worthiness",
    "cultivation.gardener_lifecycle_transition_request",
    "cultivation.gardener_routing",
    "cultivation.helper_output_staging",
    "cultivation.gardener_stub",
    "cultivation.lifecycle_candidate_lint_loop",
    "cultivation.nursery_stub",
    "cultivation.nursery_composition_input",
    "cultivation.provider_effort_vocabulary_normalization",
    "cultivation.seedkeeper",
    "cultivation.vault_record_lifecycle",
    "cultivation.vault_promotion_request",
    "delivery.mailbox_schema",
    "delivery.mailbox_contamination_guard",
    "delivery.mailbox_status",
    "delivery.mailbox_store",
    "delivery.packet_factory",
    "delivery.packet_scoring",
    "delivery.plugin_logger",
    "delivery.postman_finalization",
    "delivery.postman_gateway",
    "delivery.subagent_telemetry",
    "delivery.support_bundle",
    "evaluation.evaluator",
    "evaluation.evaluator_amundsen_handoff",
    "evaluation.chain_health_scorecard",
    "evaluation.promotion_worthiness",
    "placement.community_bridge_stub",
    "placement.map_maker_stub",
    "placement.topic_episode_placement",
    "placement.topic_episode_placement_engine",
    "placement.topic_page_filing",
    "provenance.episode_semantic_edges",
    "provenance.episode_semantic_edges_v2",
    "provenance.provenance_store",
    "reasoning.hermes_background_invocation_smoke",
    "reasoning.hermes_background_result_contract",
    "reasoning.hermes_background_task_capture",
    "reasoning.hermes_background_unavailable_contract",
    "reasoning.hermes_main_context_non_accumulation",
    "reasoning.hermes_state_metadata_policy",
    "reasoning.provider_capability_descriptor",
    "reasoning.provider_resource_boundary",
    "reasoning.provider_reasoning_gate",
    "reasoning.process_sandbox_policy",
    "reasoning.reasoning_lease_contracts",
    "reasoning.worker_hardening_policy",
    "runner.failure_fallback_regression",
    "runner.mailbox_support_emission",
    "runner.no_credential_prompt_regression",
    "runner.provider_declined_visibility",
    "runner.role_split_integration",
    "runner.same_session_answer_smoke",
    "runner.session_signal_runner",
    "runner.thin_worker_chain",
    "retrieval.graph_freshness",
    "retrieval.cross_provider_memory_consumption",
    "retrieval.graph_output_guard",
    "retrieval.graph_query_support_bundle",
    "retrieval.graph_snapshot_replacement_guard",
    "retrieval.graphify_snapshot_adapter",
    "retrieval.graphify_snapshot_manifest",
    "retrieval.graphify_snapshot_rebuild",
    "retrieval.origin_shortcut_roundtrip",
    "retrieval.pathfinder",
    "retrieval.pathfinder_ptc_mvp",
    "retrieval.pathfinder_tools",
]


COMPATIBILITY_SHIM_MODULES = [
    "admission_stub",
    "amundsen_stub",
    "community_bridge_stub",
    "decision_contracts",
    "decision_distiller",
    "episode_semantic_edges",
    "gardener_stub",
    "graph_freshness",
    "mailbox_schema",
    "mailbox_contamination_guard",
    "mailbox_status",
    "mailbox_store",
    "map_identity",
    "map_maker_stub",
    "nursery_stub",
    "packet_factory",
    "packet_scoring",
    "pathfinder",
    "pathfinder_ptc_mvp",
    "pathfinder_tools",
    "plugin_logger",
    "postman_gateway",
    "promotion_worthiness",
    "provenance_store",
    "provider_attachment",
    "provider_inbox",
    "reasoning_lease_contracts",
    "session_admission_gate",
    "seedkeeper",
    "session_structure_signal",
    "subagent_telemetry",
    "support_bundle",
    "topic_episode_placement",
    "topic_episode_placement_engine",
    "topic_page_filing",
]


RUNTIME_UTILITY_MODULES = [
    "import_hygiene",
    "shim_policy",
    "surface_policy",
]


@dataclass(frozen=True)
class ImportSmokeResult:
    imported: tuple[str, ...]
    failed: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failed


def smoke_import_modules(module_names: list[str] | tuple[str, ...]) -> ImportSmokeResult:
    imported: list[str] = []
    failed: list[str] = []
    for module_name in module_names:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            failed.append(f"{module_name}: {exc.__class__.__name__}: {exc}")
        else:
            imported.append(module_name)
    return ImportSmokeResult(imported=tuple(imported), failed=tuple(failed))


def smoke_import_runtime_surface() -> ImportSmokeResult:
    return smoke_import_modules(CANONICAL_RUNTIME_MODULES + COMPATIBILITY_SHIM_MODULES + RUNTIME_UTILITY_MODULES)
