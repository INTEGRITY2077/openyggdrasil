from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from reasoning.hermes_gateway_surface_unavailable import (
    EXPECTED_MISSING_CONDITION,
    P0_G6_SOURCE_REF,
    build_p0_official_hermes_gateway_surface_unavailable_evidence,
    validate_p0_official_hermes_gateway_surface_unavailable_evidence,
)
from reasoning.hermes_real_session_usage_probe import (
    build_hermes_real_session_usage_probe,
    validate_hermes_real_session_usage_probe,
)


R9_TYPED_UNAVAILABLE_PROJECTION_SCHEMA_VERSION = (
    "hermes_real_session_usage_unavailable_projection.v1"
)
EXPECTED_R9_UNAVAILABLE_CONDITION = "provider_owned_gateway_evidence_absent"
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
FORBIDDEN_MATERIAL_FRAGMENTS = (
    ".env",
    "api_key",
    "auth.json",
    "candidate command",
    "command material",
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


def _safe_identifier(value: Any, fallback: str) -> str:
    candidate = str(value or fallback).strip()
    return candidate if SAFE_IDENTIFIER_RE.match(candidate) else fallback


def build_hermes_real_session_usage_unavailable_proof_package(
    surface_unavailable_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Project P0-G6 surface-unavailable evidence into an R9 proof package."""

    validate_p0_official_hermes_gateway_surface_unavailable_evidence(
        surface_unavailable_evidence
    )
    if surface_unavailable_evidence.get("missing_condition") != EXPECTED_MISSING_CONDITION:
        raise ValueError("P0-G7 requires the verified P0-G6 missing_condition")

    candidate = surface_unavailable_evidence.get("candidate_package") or {}
    if not isinstance(candidate, Mapping):
        raise ValueError("P0-G7 requires P0-G6 candidate_package")

    typed_unavailable_ref = str(
        candidate.get("typed_unavailable_ref")
        or "typed-unavailable-ref://openyggdrasil/r9/provider-owned-gateway-absent"
    )
    before_ref = str(
        candidate.get("before_main_context_window_ref")
        or "context-window-ref://openyggdrasil/r9/p0-g7/before"
    )
    after_ref = str(
        candidate.get("after_main_context_window_ref")
        or "context-window-ref://openyggdrasil/r9/p0-g7/after"
    )

    return {
        "session_probe_id": _safe_identifier(
            candidate.get("session_probe_id"),
            "r9-p0-g7-surface-unavailable",
        ),
        "typed_task_id": "p0-g7-r9-typed-unavailable",
        "typed_unavailable_ref": typed_unavailable_ref,
        "before_main_context_window_ref": before_ref,
        "after_main_context_window_ref": after_ref,
        "surface_unavailable_evidence_ref": P0_G6_SOURCE_REF,
        "surface_unavailable_condition": EXPECTED_MISSING_CONDITION,
        # Intentionally omitted: provider_gateway_evidence_ref. Its absence is
        # the R9 typed-unavailable projection under current P0 truth.
        "input_schema_versions": [
            "p0_official_hermes_gateway_surface_unavailable_evidence.v1",
            "hermes_real_session_usage_probe.v1",
            R9_TYPED_UNAVAILABLE_PROJECTION_SCHEMA_VERSION,
        ],
    }


def build_hermes_real_session_usage_unavailable_projection(
    *,
    surface_unavailable_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the current R9 typed-unavailable projection from P0-G6 evidence.

    This does not perform a live Hermes session, call a provider gateway, read
    provider state, or claim R9 real-session PASS.
    """

    surface_evidence = (
        dict(surface_unavailable_evidence)
        if surface_unavailable_evidence is not None
        else build_p0_official_hermes_gateway_surface_unavailable_evidence()
    )
    validate_p0_official_hermes_gateway_surface_unavailable_evidence(surface_evidence)

    proof_package = build_hermes_real_session_usage_unavailable_proof_package(
        surface_evidence
    )
    r9_probe = build_hermes_real_session_usage_probe(proof_package=proof_package)
    validate_hermes_real_session_usage_probe(r9_probe)

    projection = {
        "schema_version": R9_TYPED_UNAVAILABLE_PROJECTION_SCHEMA_VERSION,
        "projection_status": "typed_unavailable",
        "surface_unavailable_condition": surface_evidence.get("missing_condition"),
        "proof_package": proof_package,
        "r9_probe": r9_probe,
        "proof_package_status": r9_probe.get("proof_package_status"),
        "unavailable_condition": r9_probe.get("unavailable_condition"),
        "reason_codes": [
            *_string_list(r9_probe.get("reason_codes")),
            *_string_list(surface_evidence.get("reason_codes")),
        ],
        "safe_portable_refs": _string_list(r9_probe.get("safe_portable_refs")),
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_candidate_material_included": False,
        "raw_provider_material_included": False,
        "r9_real_session_pass_claimed": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "static_projection_only": True,
        "created_at": utc_now_iso(),
    }
    validate_hermes_real_session_usage_unavailable_projection(projection)
    return projection


def validate_hermes_real_session_usage_unavailable_projection(
    projection: Mapping[str, Any],
) -> None:
    if projection.get("schema_version") != R9_TYPED_UNAVAILABLE_PROJECTION_SCHEMA_VERSION:
        raise ValueError("invalid R9 typed-unavailable projection schema_version")
    if projection.get("projection_status") != "typed_unavailable":
        raise ValueError("R9 projection must remain typed_unavailable")
    if projection.get("proof_package_status") != "typed_unavailable":
        raise ValueError("R9 probe status must be typed_unavailable")
    if projection.get("unavailable_condition") != EXPECTED_R9_UNAVAILABLE_CONDITION:
        raise ValueError("R9 projection unavailable condition mismatch")
    if projection.get("provider_gateway_called") is not False:
        raise ValueError("R9 typed-unavailable projection must not call Hermes")
    if projection.get("provider_state_read") is not False:
        raise ValueError("R9 typed-unavailable projection must not read provider state")
    if projection.get("raw_candidate_material_included") is not False:
        raise ValueError("R9 typed-unavailable projection must not include raw candidate material")
    if projection.get("raw_provider_material_included") is not False:
        raise ValueError("R9 typed-unavailable projection must not include raw provider material")
    if projection.get("r9_real_session_pass_claimed") is not False:
        raise ValueError("R9 real-session PASS must not be claimed")
    if projection.get("live_readiness_claimed") is not False:
        raise ValueError("live readiness must not be claimed")
    if projection.get("production_readiness_claimed") is not False:
        raise ValueError("production readiness must not be claimed")
    if projection.get("static_projection_only") is not True:
        raise ValueError("R9 typed-unavailable projection must remain static-only")

    proof_package = projection.get("proof_package")
    if not isinstance(proof_package, Mapping):
        raise ValueError("R9 projection requires proof_package")
    if "provider_gateway_evidence_ref" in proof_package:
        raise ValueError("R9 typed-unavailable proof_package must omit provider_gateway_evidence_ref")
    for field in (
        "session_probe_id",
        "typed_task_id",
        "typed_unavailable_ref",
        "before_main_context_window_ref",
        "after_main_context_window_ref",
    ):
        if not proof_package.get(field):
            raise ValueError(f"R9 typed-unavailable proof_package requires {field}")

    r9_probe = projection.get("r9_probe")
    if not isinstance(r9_probe, Mapping):
        raise ValueError("R9 projection requires r9_probe")
    validate_hermes_real_session_usage_probe(r9_probe)
    if r9_probe.get("provider_gateway_evidence_ref") is not None:
        raise ValueError("R9 typed-unavailable probe must not include provider gateway evidence")
    if r9_probe.get("r9_real_session_pass_claimed") is not False:
        raise ValueError("R9 probe must not claim real-session PASS")

    if (fragment := _contains_forbidden_material_value(projection)) is not None:
        raise ValueError(f"R9 projection contains forbidden material: {fragment}")

    # Keep a stable JSON-serializable shape for Worker 4 replay.
    json.dumps(dict(projection), ensure_ascii=False, sort_keys=True)
