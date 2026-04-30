from __future__ import annotations

import json
import re
import tempfile
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from reasoning.hermes_gateway_evidence_intake import (
    run_p0_official_hermes_gateway_evidence_intake,
    validate_p0_official_hermes_gateway_evidence_intake,
)
from reasoning.hermes_gateway_evidence_package import (
    TYPED_UNAVAILABLE_LIVE_PROOF,
    classify_p0_official_hermes_gateway_evidence_package,
    validate_p0_official_hermes_gateway_evidence_classification,
)


SURFACE_UNAVAILABLE_SCHEMA_VERSION = (
    "p0_official_hermes_gateway_surface_unavailable_evidence.v1"
)
EXPECTED_MISSING_CONDITION = (
    "no_current_safe_provider_owned_or_app_assigned_hermes_command_or_subagent_"
    "gateway_surface_found"
)
P0_G6_SOURCE_REF = (
    "surface-unavailable-ref://openyggdrasil/p0-g6/"
    "no-current-safe-provider-owned-or-app-assigned-hermes-gateway-surface"
)
P0_G5_VERIFICATION_REF = (
    "private-evidence://Dev_history/todo/worker4/2026-04-30/result/"
    "2026-04-30_2201_worker4_p0_g5_safe_gateway_surface_candidate_scan_verification_result.md"
)
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
FORBIDDEN_MATERIAL_FRAGMENTS = (
    ".env",
    "api_key",
    "auth.json",
    "candidate command",
    "credential",
    "foreground env",
    "private env",
    "profile",
    "prompt",
    "raw transcript",
    "secret:",
    "state.db",
    "state db",
    "stdin injection",
    "transcript",
)


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _contains_forbidden_material_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for nested in value.values():
            fragment = _contains_forbidden_material_value(nested)
            if fragment is not None:
                return fragment
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            fragment = _contains_forbidden_material_value(item)
            if fragment is not None:
                return fragment
        return None
    if isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_MATERIAL_FRAGMENTS:
            if fragment in lowered:
                return fragment
    return None


def _require_expected_missing_condition(missing_condition: str) -> str:
    condition = str(missing_condition or "").strip()
    if condition != EXPECTED_MISSING_CONDITION:
        raise ValueError("unsupported P0-G6 surface unavailable missing_condition")
    if not SAFE_IDENTIFIER_RE.match(condition):
        raise ValueError("P0-G6 missing_condition must be a safe identifier")
    return condition


def build_p0_official_hermes_gateway_surface_unavailable_candidate(
    *,
    missing_condition: str = EXPECTED_MISSING_CONDITION,
) -> dict[str, Any]:
    """Build a safe P0 candidate representing the verified absent surface."""

    condition = _require_expected_missing_condition(missing_condition)
    return {
        "schema_version": SURFACE_UNAVAILABLE_SCHEMA_VERSION,
        "provider": "hermes",
        "missing_condition": condition,
        "gateway_owner_type": "app_assigned_gateway",
        "gateway_owner_ref": "gateway-owner-ref://openyggdrasil/p0-g6/hermes/surface-unavailable",
        "invocation_surface": "official_app_assigned_command",
        "gateway_capability": "command_gateway",
        # Omitted intentionally: provider_gateway_surface_ref. Its absence is
        # the machine-checkable typed-unavailable proof for the current blocker.
        "provider_gateway_capability_ref": (
            "gateway-capability-ref://openyggdrasil/p0-g6/hermes/command-required"
        ),
        "provider_gateway_contract_ref": (
            "gateway-contract-ref://openyggdrasil/p0-g6/official-hermes-gateway-required"
        ),
        "gateway_request_ref": (
            "gateway-request-ref://openyggdrasil/p0-g6/surface-unavailable-request"
        ),
        "session_probe_id": "p0-g6-surface-unavailable",
        "typed_task_id": "p0-g6-surface-unavailable",
        "typed_result_ref": None,
        "typed_unavailable_ref": (
            "typed-unavailable-ref://openyggdrasil/p0-g6/no-current-safe-gateway-surface"
        ),
        "before_main_context_window_ref": (
            "context-window-ref://openyggdrasil/p0-g6/surface-unavailable/before"
        ),
        "after_main_context_window_ref": (
            "context-window-ref://openyggdrasil/p0-g6/surface-unavailable/after"
        ),
        "provider_gateway_evidence_ref": P0_G5_VERIFICATION_REF,
        "producer_usage_claimed": False,
        "consumer_usage_claimed": False,
        "subagent_or_provider_skill_claimed": False,
        "surface_scan_verification_ref": P0_G5_VERIFICATION_REF,
        "input_schema_versions": [
            SURFACE_UNAVAILABLE_SCHEMA_VERSION,
            "p0_official_hermes_gateway_evidence_package_classifier.v1",
            "p0_official_hermes_gateway_evidence_intake.v1",
            "p0_official_hermes_gateway_contract.v1",
        ],
    }


def _write_json(path: str | PathLike[str], payload: Mapping[str, Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def _classify_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    classification = classify_p0_official_hermes_gateway_evidence_package(candidate)
    validate_p0_official_hermes_gateway_evidence_classification(classification)
    return classification


def _run_intake_with_candidate_path(
    *,
    candidate: Mapping[str, Any],
    candidate_path: Path,
    intake_output_path: str | PathLike[str] | None,
) -> dict[str, Any]:
    _write_json(candidate_path, candidate)
    artifact = run_p0_official_hermes_gateway_evidence_intake(
        candidate_path,
        output_path=intake_output_path,
        source_ref=P0_G6_SOURCE_REF,
    )
    validate_p0_official_hermes_gateway_evidence_intake(artifact)
    return artifact


def build_p0_official_hermes_gateway_surface_unavailable_evidence(
    *,
    missing_condition: str = EXPECTED_MISSING_CONDITION,
    candidate_output_path: str | PathLike[str] | None = None,
    intake_output_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Build typed-unavailable evidence for the verified absent gateway surface.

    This function is deterministic with respect to the candidate package it
    emits. It never calls Hermes, reads provider state, executes candidate text,
    or includes raw transcript/prompt/credential/profile/state material.
    """

    condition = _require_expected_missing_condition(missing_condition)
    candidate = build_p0_official_hermes_gateway_surface_unavailable_candidate(
        missing_condition=condition
    )
    classification = _classify_candidate(candidate)

    if candidate_output_path is not None:
        candidate_path = _write_json(candidate_output_path, candidate)
        intake_artifact = _run_intake_with_candidate_path(
            candidate=candidate,
            candidate_path=candidate_path,
            intake_output_path=intake_output_path,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="openyggdrasil-p0-g6-") as temp_dir:
            candidate_path = Path(temp_dir) / "surface_unavailable_candidate.json"
            intake_artifact = _run_intake_with_candidate_path(
                candidate=candidate,
                candidate_path=candidate_path,
                intake_output_path=intake_output_path,
            )
        candidate_path = None

    result = {
        "schema_version": SURFACE_UNAVAILABLE_SCHEMA_VERSION,
        "missing_condition": condition,
        "candidate_package": candidate,
        "classification": classification,
        "intake_artifact": intake_artifact,
        "candidate_output_ref": (
            f"candidate-json-ref://openyggdrasil/p0-g6/{Path(candidate_output_path).name}"
            if candidate_output_path is not None
            else None
        ),
        "intake_output_ref": (
            f"redacted-intake-ref://openyggdrasil/p0-g6/{Path(intake_output_path).name}"
            if intake_output_path is not None
            else None
        ),
        "reason_codes": [
            condition,
            *_string_list(classification.get("reason_codes")),
            *_string_list(intake_artifact.get("reason_codes")),
        ],
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_candidate_material_included": False,
        "raw_provider_material_included": False,
        "static_builder_only": True,
        "created_at": utc_now_iso(),
    }
    validate_p0_official_hermes_gateway_surface_unavailable_evidence(result)
    return result


def validate_p0_official_hermes_gateway_surface_unavailable_evidence(
    evidence: Mapping[str, Any],
) -> None:
    if evidence.get("schema_version") != SURFACE_UNAVAILABLE_SCHEMA_VERSION:
        raise ValueError("invalid P0-G6 surface unavailable evidence schema_version")
    if evidence.get("missing_condition") != EXPECTED_MISSING_CONDITION:
        raise ValueError("invalid P0-G6 surface unavailable missing_condition")
    if evidence.get("provider_gateway_called") is not False:
        raise ValueError("P0-G6 builder must not call Hermes")
    if evidence.get("provider_state_read") is not False:
        raise ValueError("P0-G6 builder must not read provider state")
    if evidence.get("raw_candidate_material_included") is not False:
        raise ValueError("P0-G6 builder must not include raw candidate material")
    if evidence.get("raw_provider_material_included") is not False:
        raise ValueError("P0-G6 builder must not include raw provider material")
    if evidence.get("static_builder_only") is not True:
        raise ValueError("P0-G6 builder must remain static-only")

    candidate = evidence.get("candidate_package")
    if not isinstance(candidate, Mapping):
        raise ValueError("P0-G6 evidence requires candidate_package mapping")
    if candidate.get("provider") != "hermes":
        raise ValueError("P0-G6 candidate provider must be hermes")
    if candidate.get("typed_unavailable_ref") is None:
        raise ValueError("P0-G6 candidate requires typed_unavailable_ref")
    if candidate.get("provider_gateway_surface_ref") is not None:
        raise ValueError("P0-G6 candidate must not claim a current gateway surface ref")

    classification = evidence.get("classification")
    if not isinstance(classification, Mapping):
        raise ValueError("P0-G6 evidence requires classification mapping")
    validate_p0_official_hermes_gateway_evidence_classification(classification)
    if classification.get("verdict") != TYPED_UNAVAILABLE_LIVE_PROOF:
        raise ValueError("P0-G6 classification must remain typed unavailable")

    intake_artifact = evidence.get("intake_artifact")
    if not isinstance(intake_artifact, Mapping):
        raise ValueError("P0-G6 evidence requires intake_artifact mapping")
    validate_p0_official_hermes_gateway_evidence_intake(intake_artifact)
    if intake_artifact.get("verdict") != TYPED_UNAVAILABLE_LIVE_PROOF:
        raise ValueError("P0-G6 intake artifact must remain typed unavailable")

    if (fragment := _contains_forbidden_material_value(evidence)) is not None:
        raise ValueError(f"P0-G6 evidence contains forbidden material: {fragment}")
