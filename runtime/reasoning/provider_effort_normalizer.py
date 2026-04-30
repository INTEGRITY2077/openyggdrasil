from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso
from reasoning.module_effort_requirements import EFFORT_ORDER, build_module_effort_requirement


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_VERSION = "provider_reasoning_effort_normalization.v1"
SCHEMA_PATH = CONTRACTS_ROOT / f"{SCHEMA_VERSION}.schema.json"

EFFORT_BY_RANK = {rank: effort for effort, rank in EFFORT_ORDER.items()}
MODEL_CLASSES = {"below_baseline", "at_baseline", "above_baseline"}
NORMALIZATION_MODES = {"auto", "compensate_up", "pass_through", "conserve_down"}
LOW_TOKENS = {"low", "minimal", "small", "cheap", "light"}
MEDIUM_TOKENS = {"medium", "med", "normal", "default", "balanced", "standard"}
HIGH_TOKENS = {"high", "deep", "large", "hard"}
XHIGH_TOKENS = {"xhigh", "x_high", "extra_high", "extrahigh", "very_high", "max", "maximum"}

COMPENSATION_STRATEGIES_BY_MODULE = {
    "distiller": (
        "enhanced_cot_guideline",
        "split_pass_if_ambiguous",
        "double_verify_key_claims",
    ),
    "evaluator": (
        "scorecard_decomposition",
        "borderline_double_verify",
    ),
    "amundsen": (
        "taxonomy_candidate_contrast",
        "novelty_double_verify",
    ),
    "pathfinder": (
        "anchor_candidate_contrast",
        "source_support_double_check",
    ),
    "ptc_substrate": (
        "plan_step_budgeting",
        "capability_trace_double_check",
    ),
}


@lru_cache(maxsize=1)
def load_provider_reasoning_effort_normalization_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_provider_reasoning_effort_normalization(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_provider_reasoning_effort_normalization_schema(),
    )
    normalization = dict(payload["normalization"])
    module_effort = dict(payload["module_effort"])
    if not module_effort["requires_reasoning"]:
        if normalization["mode"] != "deterministic_no_reasoning":
            raise ValueError("deterministic modules must not request reasoning normalization")
        if normalization["selected_effort"] != "none":
            raise ValueError("deterministic modules must select none effort")
    if normalization["mode"] == "compensate_up" and not normalization["compensation_strategies"]:
        raise ValueError("compensate_up requires compensation strategies")
    if normalization["mode"] != "conserve_down" and normalization["below_module_min_effort_allowed"]:
        raise ValueError("only conserve_down may allow selected effort below baseline module minimum")


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_reasoning_tier(value: Any) -> str:
    token = _token(value)
    if token in EFFORT_ORDER:
        return token
    if token in LOW_TOKENS:
        return "low"
    if token in MEDIUM_TOKENS:
        return "medium"
    if token in HIGH_TOKENS:
        return "high"
    if token in XHIGH_TOKENS:
        return "xhigh"
    raise ValueError("unknown provider reasoning_tier")


def normalize_model_class(value: Any) -> str:
    token = _token(value)
    if token in MODEL_CLASSES:
        return token
    raise ValueError("unknown provider model_class")


def normalize_requested_normalization(value: Any) -> str:
    token = _token(value) or "auto"
    if token in NORMALIZATION_MODES:
        return token
    raise ValueError("unknown requested_normalization")


def _step_down(effort: str) -> str:
    rank = max(EFFORT_ORDER["none"], EFFORT_ORDER[effort] - 1)
    return EFFORT_BY_RANK[rank]


def _max_effort(left: str, right: str) -> str:
    return left if EFFORT_ORDER[left] >= EFFORT_ORDER[right] else right


def _normalization_mode(*, model_class: str, requested_normalization: str) -> str:
    if requested_normalization != "auto":
        return requested_normalization
    if model_class == "below_baseline":
        return "compensate_up"
    if model_class == "above_baseline":
        return "conserve_down"
    return "pass_through"


def _provider_capability(provider_capability: Mapping[str, Any]) -> dict[str, str]:
    required = ("provider_id", "model_class", "reasoning_tier", "requested_normalization")
    missing = [key for key in required if not str(provider_capability.get(key) or "").strip()]
    if missing:
        raise ValueError("provider capability declaration missing required fields: " + ", ".join(missing))
    model_class = normalize_model_class(provider_capability["model_class"])
    return {
        "provider_id": str(provider_capability["provider_id"]).strip(),
        "model_class": model_class,
        "reasoning_tier": normalize_reasoning_tier(provider_capability["reasoning_tier"]),
        "requested_normalization": normalize_requested_normalization(
            provider_capability["requested_normalization"]
        ),
    }


def build_provider_reasoning_effort_normalization(
    *,
    provider_capability: Mapping[str, Any],
    module_id: str,
) -> dict[str, Any]:
    """Normalize provider-relative reasoning effort for one openyggdrasil module.

    This is not raw vocabulary normalization. It turns a provider's relative
    model capability declaration into an execution decision: compensate weak
    models with stronger guidance, pass through baseline models, or conserve
    tokens for stronger-than-baseline models.
    """

    capability = _provider_capability(provider_capability)
    requirement = build_module_effort_requirement(str(module_id).strip().lower())
    module_effort = {
        "requires_reasoning": bool(requirement["requires_reasoning"]),
        "min_effort": str(requirement["min_effort"]),
        "preferred_effort": str(requirement["preferred_effort"]),
        "max_useful_effort": str(requirement["max_useful_effort"]),
        "lease_group": str(requirement["lease_group"]),
    }
    baseline = module_effort["preferred_effort"]
    reason_codes = [
        "provider_relative_effort_normalized",
        f"module:{requirement['module_id']}",
    ]

    if not module_effort["requires_reasoning"]:
        mode = "deterministic_no_reasoning"
        selected_effort = "none"
        strategies: list[str] = []
        compensation_required = False
        token_conservation = False
        below_min_allowed = False
        guidance_intensity = "none"
        reason_codes.append("deterministic_module_no_reasoning_tokens")
    else:
        mode = _normalization_mode(
            model_class=capability["model_class"],
            requested_normalization=capability["requested_normalization"],
        )
        if mode == "compensate_up":
            selected_effort = _max_effort(baseline, capability["reasoning_tier"])
            selected_effort = _max_effort(selected_effort, module_effort["min_effort"])
            selected_effort = (
                module_effort["max_useful_effort"]
                if EFFORT_ORDER[selected_effort] > EFFORT_ORDER[module_effort["max_useful_effort"]]
                else selected_effort
            )
            strategies = list(COMPENSATION_STRATEGIES_BY_MODULE.get(str(requirement["module_id"]), ()))
            if not strategies:
                strategies = ["structured_step_by_step_guideline", "result_double_check"]
            compensation_required = True
            token_conservation = False
            below_min_allowed = False
            guidance_intensity = "strong"
            reason_codes.extend(
                [
                    "provider_below_baseline_compensate_up",
                    "compensation_guidance_required",
                ]
            )
        elif mode == "conserve_down":
            selected_effort = _step_down(baseline)
            strategies = []
            compensation_required = False
            token_conservation = True
            below_min_allowed = EFFORT_ORDER[selected_effort] < EFFORT_ORDER[module_effort["min_effort"]]
            guidance_intensity = "normal"
            reason_codes.extend(
                [
                    "provider_above_baseline_conserve_down",
                    "token_conservation_applied",
                ]
            )
            if below_min_allowed:
                reason_codes.append("provider_strength_offsets_lower_selected_effort")
        else:
            mode = "pass_through"
            selected_effort = baseline
            strategies = []
            compensation_required = False
            token_conservation = False
            below_min_allowed = False
            guidance_intensity = "normal"
            reason_codes.append("provider_at_baseline_pass_through")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "normalization_id": uuid.uuid4().hex,
        "provider_capability": capability,
        "module_id": str(requirement["module_id"]),
        "module_effort": module_effort,
        "normalization": {
            "mode": mode,
            "selected_effort": selected_effort,
            "baseline_effort": baseline,
            "provider_reasoning_tier": capability["reasoning_tier"],
            "compensation_required": compensation_required,
            "compensation_strategies": strategies,
            "token_conservation_applied": token_conservation,
            "below_module_min_effort_allowed": below_min_allowed,
            "guidance_intensity": guidance_intensity,
        },
        "safety": {
            "raw_provider_effort_equivalence_claimed": False,
            "provider_capability_overrides_module_contract": False,
            "live_readiness_claimed": False,
            "production_readiness_claimed": False,
        },
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "created_at": utc_now_iso(),
    }
    validate_provider_reasoning_effort_normalization(payload)
    return payload


__all__ = [
    "build_provider_reasoning_effort_normalization",
    "load_provider_reasoning_effort_normalization_schema",
    "normalize_model_class",
    "normalize_reasoning_tier",
    "normalize_requested_normalization",
    "validate_provider_reasoning_effort_normalization",
]
