from __future__ import annotations

from typing import Any, Mapping, Sequence


POLICY_SCHEMA_VERSION = "reasoning_chain_bundle_policy.v1"

CHAIN_BUNDLE_POLICIES: dict[str, dict[str, Any]] = {
    "ingress_chain": {
        "schema_version": POLICY_SCHEMA_VERSION,
        "chain_id": "ingress_chain",
        "status": "active",
        "module_ids": ("distiller", "evaluator", "amundsen"),
        "bundle_strategy": "single_bwrap_sequential",
        "collection_window_ms": 100,
        "max_time_budget_seconds": 900,
        "reason_codes": (
            "ingress_chain_bundle_policy",
            "phase4_reasoning_tollgate_active",
        ),
    },
    "egress_chain": {
        "schema_version": POLICY_SCHEMA_VERSION,
        "chain_id": "egress_chain",
        "status": "declared_phase5",
        "module_ids": ("pathfinder", "ptc_substrate"),
        "bundle_strategy": "deferred",
        "collection_window_ms": 100,
        "max_time_budget_seconds": 600,
        "reason_codes": ("phase5_activation_required",),
    },
    "maintenance_chain": {
        "schema_version": POLICY_SCHEMA_VERSION,
        "chain_id": "maintenance_chain",
        "status": "declared_phase5",
        "module_ids": ("gardener", "graphify_extract"),
        "bundle_strategy": "deferred",
        "collection_window_ms": 100,
        "max_time_budget_seconds": 600,
        "reason_codes": ("phase5_activation_required",),
    },
}


def normalize_module_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def get_chain_bundle_policy(chain_id: str) -> dict[str, Any]:
    normalized = normalize_module_id(chain_id)
    if normalized not in CHAIN_BUNDLE_POLICIES:
        raise ValueError(f"unknown chain bundle policy: {chain_id}")
    policy = dict(CHAIN_BUNDLE_POLICIES[normalized])
    policy["module_ids"] = list(policy["module_ids"])
    policy["reason_codes"] = list(policy["reason_codes"])
    validate_chain_bundle_policy(policy)
    return policy


def select_chain_bundle_policy(module_ids: Sequence[str]) -> dict[str, Any] | None:
    requested = {normalize_module_id(module_id) for module_id in module_ids}
    for chain_id, raw_policy in CHAIN_BUNDLE_POLICIES.items():
        policy_modules = {normalize_module_id(module_id) for module_id in raw_policy["module_ids"]}
        if raw_policy["status"] == "active" and requested and requested.issubset(policy_modules):
            return get_chain_bundle_policy(chain_id)
    return None


def build_chain_bundle_policy_manifest() -> dict[str, Any]:
    active = [chain_id for chain_id, policy in CHAIN_BUNDLE_POLICIES.items() if policy["status"] == "active"]
    return {
        "schema_version": "reasoning_chain_bundle_policy_manifest.v1",
        "policies": [get_chain_bundle_policy(chain_id) for chain_id in CHAIN_BUNDLE_POLICIES],
        "active_chain_ids": active,
        "deferred_chain_ids": [chain_id for chain_id in CHAIN_BUNDLE_POLICIES if chain_id not in active],
    }


def validate_chain_bundle_policy(policy: Mapping[str, Any]) -> None:
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("invalid chain bundle policy schema_version")
    if not policy.get("chain_id"):
        raise ValueError("chain bundle policy requires chain_id")
    module_ids = policy.get("module_ids")
    if not isinstance(module_ids, Sequence) or isinstance(module_ids, (str, bytes)):
        raise ValueError("chain bundle policy requires module_ids")
    if not module_ids:
        raise ValueError("chain bundle policy requires at least one module")
    for field in ("collection_window_ms", "max_time_budget_seconds"):
        if int(policy.get(field, 0)) <= 0:
            raise ValueError(f"chain bundle policy requires positive {field}")
