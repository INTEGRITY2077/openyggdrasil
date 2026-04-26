from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

EFFORT_ORDER = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "xhigh": 4,
}
DEFAULT_CHAIN_MODULES = (
    "distiller",
    "evaluator",
    "amundsen",
    "pathfinder",
    "seedkeeper",
    "gardener",
    "map_maker",
    "postman",
)
TARGET_PLATFORM_POLICY = "wsl2_linux_first_native_windows_deferred"
SANDBOX_BACKEND_POLICY = "sandbox-runtime:bubblewrap_on_wsl2_linux"

MODULE_EFFORT_DEFAULTS: dict[str, dict[str, Any]] = {
    "distiller": {
        "requires_reasoning": True,
        "min_effort": "high",
        "preferred_effort": "high",
        "max_useful_effort": "xhigh",
        "reasoning_depth_area": "response_quality",
        "lease_group": "deep_reasoning",
        "sandbox_required": True,
        "effort_justification_code": "long_context_distillation",
        "target_runtime_module": "runtime/capture/decision_distiller.py",
    },
    "evaluator": {
        "requires_reasoning": True,
        "min_effort": "high",
        "preferred_effort": "high",
        "max_useful_effort": "xhigh",
        "reasoning_depth_area": "response_quality",
        "lease_group": "deep_reasoning",
        "sandbox_required": True,
        "effort_justification_code": "semantic_worthiness_review",
        "target_runtime_module": "runtime/evaluation/evaluator.py",
    },
    "amundsen": {
        "requires_reasoning": True,
        "min_effort": "medium",
        "preferred_effort": "medium",
        "max_useful_effort": "high",
        "reasoning_depth_area": "retrieval_relevance",
        "lease_group": "semantic_routing",
        "sandbox_required": True,
        "effort_justification_code": "synonym_typo_resolution",
        "target_runtime_module": "runtime/admission/amundsen_stub.py",
    },
    "pathfinder": {
        "requires_reasoning": True,
        "min_effort": "medium",
        "preferred_effort": "medium",
        "max_useful_effort": "high",
        "reasoning_depth_area": "retrieval_relevance",
        "lease_group": "semantic_routing",
        "sandbox_required": True,
        "effort_justification_code": "semantic_pathfinding",
        "target_runtime_module": "runtime/retrieval/pathfinder.py",
    },
    "seedkeeper": {
        "requires_reasoning": False,
        "min_effort": "none",
        "preferred_effort": "none",
        "max_useful_effort": "none",
        "reasoning_depth_area": "none",
        "lease_group": "deterministic",
        "sandbox_required": False,
        "effort_justification_code": "deterministic_structure_only",
        "target_runtime_module": "runtime/cultivation/seedkeeper.py",
    },
    "gardener": {
        "requires_reasoning": False,
        "min_effort": "none",
        "preferred_effort": "none",
        "max_useful_effort": "none",
        "reasoning_depth_area": "none",
        "lease_group": "deterministic",
        "sandbox_required": False,
        "effort_justification_code": "deterministic_vault_io",
        "target_runtime_module": "runtime/cultivation/gardener_stub.py",
    },
    "map_maker": {
        "requires_reasoning": False,
        "min_effort": "none",
        "preferred_effort": "none",
        "max_useful_effort": "none",
        "reasoning_depth_area": "none",
        "lease_group": "deterministic",
        "sandbox_required": False,
        "effort_justification_code": "deterministic_map_update",
        "target_runtime_module": "runtime/placement/map_maker_stub.py",
    },
    "postman": {
        "requires_reasoning": False,
        "min_effort": "none",
        "preferred_effort": "none",
        "max_useful_effort": "none",
        "reasoning_depth_area": "none",
        "lease_group": "deterministic",
        "sandbox_required": False,
        "effort_justification_code": "deterministic_delivery_formatting",
        "target_runtime_module": "runtime/delivery/postman_finalization.py",
    },
}


def _load_schema(filename: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_module_effort_requirement_schema() -> dict[str, Any]:
    return _load_schema("module_effort_requirement.v1.schema.json")


@lru_cache(maxsize=1)
def load_module_effort_plan_schema() -> dict[str, Any]:
    return _load_schema("module_effort_plan.v1.schema.json")


def validate_module_effort_requirement(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_module_effort_requirement_schema())


def validate_module_effort_plan(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_module_effort_plan_schema())


def _assert_effort_order(requirement: Mapping[str, Any]) -> None:
    minimum = str(requirement["min_effort"])
    preferred = str(requirement["preferred_effort"])
    maximum = str(requirement["max_useful_effort"])
    if not (EFFORT_ORDER[minimum] <= EFFORT_ORDER[preferred] <= EFFORT_ORDER[maximum]):
        raise ValueError("module effort order must be min <= preferred <= max_useful")
    if not requirement["requires_reasoning"]:
        if (minimum, preferred, maximum) != ("none", "none", "none"):
            raise ValueError("deterministic modules must use none effort")
        if requirement["sandbox_required"]:
            raise ValueError("deterministic modules must not require sandboxed reasoning lease execution")
        if requirement["lease_group"] != "deterministic":
            raise ValueError("deterministic modules must use deterministic lease_group")


def build_module_effort_requirement(module_id: str) -> dict[str, Any]:
    if module_id not in MODULE_EFFORT_DEFAULTS:
        raise ValueError(f"unknown module effort requirement: {module_id}")
    payload = {
        "schema_version": "module_effort_requirement.v1",
        "module_id": module_id,
        **MODULE_EFFORT_DEFAULTS[module_id],
        "plain_text_effort_allowed": False,
        "reason_codes": [
            "module_effort_contract_required",
            f"module:{module_id}",
        ],
    }
    _assert_effort_order(payload)
    validate_module_effort_requirement(payload)
    return payload


def build_default_module_effort_requirements(
    module_ids: Sequence[str] = DEFAULT_CHAIN_MODULES,
) -> list[dict[str, Any]]:
    return [build_module_effort_requirement(module_id) for module_id in module_ids]


def _max_effort(requirements: Sequence[Mapping[str, Any]], field: str) -> str:
    if not requirements:
        return "none"
    return max((str(requirement[field]) for requirement in requirements), key=EFFORT_ORDER.__getitem__)


def _lease_group_payload(lease_group: str, requirements: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "lease_group": lease_group,
        "module_ids": [str(requirement["module_id"]) for requirement in requirements],
        "required_effort": _max_effort(requirements, "min_effort"),
        "preferred_effort": _max_effort(requirements, "preferred_effort"),
        "inference_mode": "provider_headless",
        "sandbox_required": True,
        "sandbox_backend_policy": SANDBOX_BACKEND_POLICY,
    }


def build_module_effort_plan(
    module_ids: Sequence[str] = DEFAULT_CHAIN_MODULES,
    *,
    chain_id: str = "thin_worker_chain",
) -> dict[str, Any]:
    requirements = build_default_module_effort_requirements(module_ids)
    reasoning_modules = [requirement for requirement in requirements if requirement["requires_reasoning"]]
    deterministic_modules = [requirement for requirement in requirements if not requirement["requires_reasoning"]]
    lease_groups: list[dict[str, Any]] = []
    for lease_group in ("deep_reasoning", "semantic_routing"):
        grouped = [requirement for requirement in reasoning_modules if requirement["lease_group"] == lease_group]
        if grouped:
            lease_groups.append(_lease_group_payload(lease_group, grouped))

    plan = {
        "schema_version": "module_effort_plan.v1",
        "plan_id": uuid.uuid4().hex,
        "chain_id": chain_id,
        "target_platform_policy": TARGET_PLATFORM_POLICY,
        "plain_text_effort_allowed": False,
        "reasoning_modules": reasoning_modules,
        "deterministic_modules": deterministic_modules,
        "lease_groups": lease_groups,
        "chain_min_effort": _max_effort(reasoning_modules, "min_effort"),
        "chain_preferred_effort": _max_effort(reasoning_modules, "preferred_effort"),
        "reasoning_module_count": len(reasoning_modules),
        "deterministic_module_count": len(deterministic_modules),
        "reason_codes": [
            "module_effort_plan_built",
            "split_lease_groups_required",
            "wsl2_linux_first_sandbox_policy",
        ],
    }
    validate_module_effort_plan(plan)
    return plan
