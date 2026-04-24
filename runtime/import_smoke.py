from __future__ import annotations

import importlib
from dataclasses import dataclass


CANONICAL_RUNTIME_MODULES = [
    "admission.admission_stub",
    "admission.amundsen_stub",
    "admission.decision_contracts",
    "admission.session_admission_gate",
    "attachments.bootstrap_contract",
    "attachments.provider_attachment",
    "attachments.provider_inbox",
    "capture.decision_distiller",
    "capture.session_structure_signal",
    "common.map_identity",
    "cultivation.gardener_stub",
    "cultivation.nursery_stub",
    "delivery.mailbox_schema",
    "delivery.mailbox_contamination_guard",
    "delivery.mailbox_status",
    "delivery.mailbox_store",
    "delivery.packet_factory",
    "delivery.packet_scoring",
    "delivery.plugin_logger",
    "delivery.postman_gateway",
    "delivery.subagent_telemetry",
    "delivery.support_bundle",
    "evaluation.promotion_worthiness",
    "placement.community_bridge_stub",
    "placement.map_maker_stub",
    "placement.topic_episode_placement",
    "placement.topic_episode_placement_engine",
    "placement.topic_page_filing",
    "provenance.episode_semantic_edges",
    "provenance.episode_semantic_edges_v2",
    "provenance.provenance_store",
    "reasoning.provider_resource_boundary",
    "reasoning.reasoning_lease_contracts",
    "retrieval.graph_freshness",
    "retrieval.graphify_snapshot_adapter",
    "retrieval.graphify_snapshot_manifest",
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
    "session_structure_signal",
    "subagent_telemetry",
    "support_bundle",
    "topic_episode_placement",
    "topic_episode_placement_engine",
    "topic_page_filing",
]


RUNTIME_UTILITY_MODULES = [
    "shim_policy",
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
