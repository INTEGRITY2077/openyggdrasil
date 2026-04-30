from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso
from reasoning.provider_effort_normalizer import (
    normalize_model_class,
    normalize_reasoning_tier,
    normalize_requested_normalization,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_VERSION = "provider_reasoning_self_assessment.v1"
SCHEMA_PATH = CONTRACTS_ROOT / f"{SCHEMA_VERSION}.schema.json"

MODEL_ROLES = {"main_provider", "subagent_provider"}
CONFIDENCE_VALUES = {"low", "medium", "high"}
EVIDENCE_BASIS_VALUES = {
    "self_assessed_only",
    "known_model_map",
    "calibrated_probe",
    "official_doc",
    "mixed",
}


@lru_cache(maxsize=1)
def load_provider_reasoning_self_assessment_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_provider_reasoning_self_assessment(payload: Mapping[str, Any]) -> None:
    assessment = dict(payload)
    jsonschema.validate(
        instance=assessment,
        schema=load_provider_reasoning_self_assessment_schema(),
    )
    status = assessment["assessment_status"]
    decision = dict(assessment["decision"])
    subjects = list(assessment["subjects"])
    if status == "self_assessed":
        if not subjects:
            raise ValueError("self_assessed status requires at least one subject")
        if decision["provider_capability_for_normalizer"] is None:
            raise ValueError("self_assessed status requires provider_capability_for_normalizer")
        if decision["requested_normalization"] == "typed_unavailable":
            raise ValueError("self_assessed status must not use typed_unavailable normalization")
    if status == "typed_unavailable":
        if decision["provider_capability_for_normalizer"] is not None:
            raise ValueError("typed_unavailable status must not emit provider_capability_for_normalizer")
        if decision["requested_normalization"] != "typed_unavailable":
            raise ValueError("typed_unavailable status requires typed_unavailable normalization")
    if assessment["safety"]["self_assessment_not_verified"] is not True:
        raise ValueError("provider self assessment must remain unverified unless externally proven")


def _identifier(value: Any, *, fallback: str | None = None) -> str:
    text = str(value or fallback or "").strip().replace(" ", "_")
    if not text:
        raise ValueError("identifier is required")
    return text[:128]


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _subject(
    *,
    provider_id: str,
    model_role: str,
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    role = _token(model_role)
    if role not in MODEL_ROLES:
        raise ValueError("unknown model_role")
    confidence = _token(assessment.get("confidence", "low"))
    if confidence not in CONFIDENCE_VALUES:
        raise ValueError("unknown confidence")
    evidence_basis = _token(assessment.get("evidence_basis", "self_assessed_only"))
    if evidence_basis not in EVIDENCE_BASIS_VALUES:
        raise ValueError("unknown evidence_basis")
    return {
        "subject_id": _identifier(
            assessment.get("subject_id"),
            fallback=f"{provider_id}:{role}",
        ),
        "model_role": role,
        "model_class": normalize_model_class(assessment.get("model_class")),
        "reasoning_tier": normalize_reasoning_tier(assessment.get("reasoning_tier")),
        "confidence": confidence,
        "evidence_basis": evidence_basis,
        "limitation_codes": [
            _identifier(code)
            for code in assessment.get("limitation_codes", ["self_assessment_not_verified"])
        ],
    }


def _typed_unavailable_payload(*, provider_id: str, module_id: str, reason_code: str) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "assessment_id": uuid.uuid4().hex,
        "provider_id": _identifier(provider_id),
        "module_id": _identifier(module_id),
        "assessment_status": "typed_unavailable",
        "subjects": [],
        "decision": {
            "selected_subject_id": None,
            "selected_model_role": None,
            "requested_normalization": "typed_unavailable",
            "decision_basis": "insufficient_signal",
            "provider_capability_for_normalizer": None,
        },
        "safety": {
            "self_assessment_not_verified": True,
            "verified_capability_claimed": False,
            "provider_capability_overrides_module_contract": False,
            "raw_prompt_included": False,
            "raw_transcript_included": False,
            "live_readiness_claimed": False,
            "production_readiness_claimed": False,
        },
        "reason_codes": [reason_code, "provider_reasoning_self_assessment_unavailable"],
        "created_at": utc_now_iso(),
    }
    validate_provider_reasoning_self_assessment(payload)
    return payload


def build_provider_reasoning_self_assessment(
    *,
    provider_id: str,
    module_id: str,
    main_model_assessment: Mapping[str, Any] | None = None,
    subagent_model_assessment: Mapping[str, Any] | None = None,
    preferred_model_role: str = "subagent_provider",
) -> dict[str, Any]:
    """Build the provider's own model-capability decision as typed input.

    The result is deliberately self-assessed, not verified. It can feed
    provider_effort_normalizer only as a declared model capability.
    """

    normalized_provider_id = _identifier(provider_id)
    normalized_module_id = _identifier(module_id)
    subjects: list[dict[str, Any]] = []
    try:
        if main_model_assessment is not None:
            subjects.append(
                _subject(
                    provider_id=normalized_provider_id,
                    model_role="main_provider",
                    assessment=main_model_assessment,
                )
            )
        if subagent_model_assessment is not None:
            subjects.append(
                _subject(
                    provider_id=normalized_provider_id,
                    model_role="subagent_provider",
                    assessment=subagent_model_assessment,
                )
            )
    except Exception as exc:
        return _typed_unavailable_payload(
            provider_id=normalized_provider_id,
            module_id=normalized_module_id,
            reason_code=f"invalid_self_assessment:{exc.__class__.__name__}",
        )

    if not subjects:
        return _typed_unavailable_payload(
            provider_id=normalized_provider_id,
            module_id=normalized_module_id,
            reason_code="model_capability_self_assessment_absent",
        )

    preferred = _token(preferred_model_role)
    selected = next((subject for subject in subjects if subject["model_role"] == preferred), subjects[0])
    requested_normalization = normalize_requested_normalization(
        (
            subagent_model_assessment
            if selected["model_role"] == "subagent_provider"
            else main_model_assessment
        )
        .get("requested_normalization", "auto")
    )
    provider_capability = {
        "provider_id": normalized_provider_id,
        "model_class": selected["model_class"],
        "reasoning_tier": selected["reasoning_tier"],
        "requested_normalization": requested_normalization,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "assessment_id": uuid.uuid4().hex,
        "provider_id": normalized_provider_id,
        "module_id": normalized_module_id,
        "assessment_status": "self_assessed",
        "subjects": subjects,
        "decision": {
            "selected_subject_id": selected["subject_id"],
            "selected_model_role": selected["model_role"],
            "requested_normalization": requested_normalization,
            "decision_basis": selected["evidence_basis"],
            "provider_capability_for_normalizer": provider_capability,
        },
        "safety": {
            "self_assessment_not_verified": True,
            "verified_capability_claimed": False,
            "provider_capability_overrides_module_contract": False,
            "raw_prompt_included": False,
            "raw_transcript_included": False,
            "live_readiness_claimed": False,
            "production_readiness_claimed": False,
        },
        "reason_codes": [
            "provider_reasoning_self_assessed",
            f"selected:{selected['model_role']}",
            f"basis:{selected['evidence_basis']}",
        ],
        "created_at": utc_now_iso(),
    }
    validate_provider_reasoning_self_assessment(payload)
    return payload


__all__ = [
    "build_provider_reasoning_self_assessment",
    "load_provider_reasoning_self_assessment_schema",
    "validate_provider_reasoning_self_assessment",
]
