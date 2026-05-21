from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
import operator as _stdlib_operator  # noqa: F401 - pins stdlib operator in sys.modules


def _ensure_runtime_package_loaded() -> None:
    if "runtime" in sys.modules:
        return
    runtime_root = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "runtime",
        runtime_root / "__init__.py",
        submodule_search_locations=[str(runtime_root)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runtime package from {runtime_root}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["runtime"] = module
    spec.loader.exec_module(module)


_ensure_runtime_package_loaded()

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS


CANONICAL_RUNTIME_MODULES = [
    "admission.admission_stub",
    "admission.amundsen_stub",
    "admission.amundsen_nursery_handoff",
    "admission.decision_contracts",
    "admission.session_admission_gate",
    "attachments.bootstrap_contract",
    "attachments.provider_attachment",
    "attachments.provider_cold_start_healthcheck",
    "attachments.provider_inbox",
    "attachments.provider_tooling_classification",
    "capture.boundary_ledger",
    "capture.decision_distiller",
    "capture.context_guard",
    "capture.live_compaction_observer",
    "capture.provider_current_source_bridge",
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
    "cultivation.wiki_vault_janitor",
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
    "delivery.postman_heartbeat_cpr",
    "delivery.subagent_telemetry",
    "delivery.support_bundle",
    "delivery.typed_unavailable_result",
    "evaluation.evaluator",
    "evaluation.evaluator_amundsen_handoff",
    "evaluation.promotion_worthiness",
    "evaluation.why_remembered_answer",
    "placement.community_bridge_stub",
    "placement.map_maker_stub",
    "placement.topic_index_catalog",
    "placement.topic_episode_placement",
    "placement.topic_episode_placement_engine",
    "placement.topic_page_filing",
    "provenance.episode_semantic_edges",
    "provenance.episode_semantic_edges_v2",
    "provenance.provenance_store",
    "reasoning.hermes_main_context_non_accumulation",
    "reasoning.hermes_state_metadata_policy",
    "reasoning.chain_bundle_policy",
    "reasoning.lease_executor",
    "reasoning.lease_tollgate",
    "reasoning.module_effort_requirements",
    "reasoning.persona_loader",
    "reasoning.ptc_bubblewrap_isolation_trace",
    "reasoning.provider_capability_descriptor",
    "reasoning.provider_effort_normalizer",
    "reasoning.provider_reasoning_self_assessment",
    "reasoning.provider_resource_boundary",
    "reasoning.provider_reasoning_gate",
    "reasoning.process_sandbox_policy",
    "reasoning.reasoning_lease_contracts",
    "reasoning.typed_availability_metrics",
    "reasoning.worker_hardening_policy",
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
    "retrieval.pathfinder_bundle_builder",
    "retrieval.pathfinder_contracts",
    "retrieval.pathfinder_lifecycle",
    "retrieval.pathfinder_mailbox",
    "retrieval.pathfinder_product_route",
    "retrieval.pathfinder_ptc_mvp",
    "retrieval.pathfinder_tools",
    "wiki.best_case_alignment_gate",
    "wiki.content_first_article_renderer",
    "wiki.content_first_gate",
    "wiki.operation",
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
    "postman_heartbeat_cpr",
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
        import_name = module_name if module_name.startswith("runtime.") else f"runtime.{module_name}"
        try:
            importlib.import_module(import_name)
        except RECOVERABLE_RUNTIME_ERRORS as exc:
            failed.append(f"{import_name}: {exc.__class__.__name__}: {exc}")
        else:
            imported.append(import_name)
    return ImportSmokeResult(imported=tuple(imported), failed=tuple(failed))


def smoke_import_runtime_surface() -> ImportSmokeResult:
    return smoke_import_modules(CANONICAL_RUNTIME_MODULES + COMPATIBILITY_SHIM_MODULES + RUNTIME_UTILITY_MODULES)


def main() -> int:
    result = smoke_import_runtime_surface()
    payload = {
        "ok": result.ok,
        "imported_count": len(result.imported),
        "failed_count": len(result.failed),
        "failed": list(result.failed),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
