from __future__ import annotations

from dataclasses import dataclass


SHIM_POLICY_VERSION = "runtime-shim-policy.v1"
SHIM_RETENTION_STATUS = "retain_until_provider_imports_migrate"

COMPATIBILITY_SHIM_TARGETS = {
    "admission_stub": "admission.admission_stub",
    "amundsen_stub": "admission.amundsen_stub",
    "community_bridge_stub": "placement.community_bridge_stub",
    "decision_contracts": "admission.decision_contracts",
    "decision_distiller": "capture.decision_distiller",
    "episode_semantic_edges": "provenance.episode_semantic_edges",
    "gardener_stub": "cultivation.gardener_stub",
    "graph_freshness": "retrieval.graph_freshness",
    "mailbox_contamination_guard": "delivery.mailbox_contamination_guard",
    "mailbox_schema": "delivery.mailbox_schema",
    "mailbox_status": "delivery.mailbox_status",
    "mailbox_store": "delivery.mailbox_store",
    "map_identity": "common.map_identity",
    "map_maker_stub": "placement.map_maker_stub",
    "nursery_stub": "cultivation.nursery_stub",
    "packet_factory": "delivery.packet_factory",
    "packet_scoring": "delivery.packet_scoring",
    "pathfinder": "retrieval.pathfinder",
    "pathfinder_ptc_mvp": "retrieval.pathfinder_ptc_mvp",
    "pathfinder_tools": "retrieval.pathfinder_tools",
    "plugin_logger": "delivery.plugin_logger",
    "postman_gateway": "delivery.postman_gateway",
    "promotion_worthiness": "evaluation.promotion_worthiness",
    "provenance_store": "provenance.provenance_store",
    "provider_attachment": "attachments.provider_attachment",
    "provider_inbox": "attachments.provider_inbox",
    "reasoning_lease_contracts": "reasoning.reasoning_lease_contracts",
    "session_admission_gate": "admission.session_admission_gate",
    "seedkeeper": "cultivation.seedkeeper",
    "session_structure_signal": "capture.session_structure_signal",
    "subagent_telemetry": "delivery.subagent_telemetry",
    "support_bundle": "delivery.support_bundle",
    "topic_episode_placement": "placement.topic_episode_placement",
    "topic_episode_placement_engine": "placement.topic_episode_placement_engine",
    "topic_page_filing": "placement.topic_page_filing",
}

TOP_LEVEL_RUNTIME_UTILITIES = {
    "antigravity_router_bootstrap",
    "harness_common",
    "hermes_attachment_reliability",
    "hermes_foreground_probe",
    "import_smoke",
    "map_maker_quality",
    "prove_antigravity_live_skill_attach",
    "prove_antigravity_router_bootstrap",
    "prove_antigravity_skill_monitor",
    "prove_hermes_attachment_reliability",
    "prove_hermes_foreground_probe",
    "prove_provider_skill_attachment",
    "shim_policy",
}


@dataclass(frozen=True)
class ShimPolicyDecision:
    module_name: str
    classification: str
    canonical_target: str | None
    retention_status: str


def canonical_target_for(module_name: str) -> str | None:
    normalized = module_name.removesuffix(".py")
    return COMPATIBILITY_SHIM_TARGETS.get(normalized)


def classify_top_level_module(module_name: str) -> ShimPolicyDecision:
    normalized = module_name.removesuffix(".py")
    canonical_target = canonical_target_for(normalized)
    if canonical_target is not None:
        return ShimPolicyDecision(
            module_name=normalized,
            classification="compatibility_shim",
            canonical_target=canonical_target,
            retention_status=SHIM_RETENTION_STATUS,
        )
    if normalized in TOP_LEVEL_RUNTIME_UTILITIES:
        return ShimPolicyDecision(
            module_name=normalized,
            classification="runtime_utility",
            canonical_target=None,
            retention_status="retain_as_named_entrypoint",
        )
    return ShimPolicyDecision(
        module_name=normalized,
        classification="unknown",
        canonical_target=None,
        retention_status="requires_review_before_commit",
    )


def shim_policy_summary() -> dict[str, object]:
    return {
        "schema_version": SHIM_POLICY_VERSION,
        "compatibility_shim_count": len(COMPATIBILITY_SHIM_TARGETS),
        "top_level_utility_count": len(TOP_LEVEL_RUNTIME_UTILITIES),
        "retention_status": SHIM_RETENTION_STATUS,
    }
