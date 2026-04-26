from __future__ import annotations

from typing import Any, Mapping, Sequence


UNAVAILABLE_DECISION_VALUES = {
    "blocked",
    "declined",
    "degraded",
    "failed",
    "not_ready",
    "unavailable",
}


def _as_mapping(payload: object) -> Mapping[str, Any]:
    return payload if isinstance(payload, Mapping) else {}


def _decision_value(payload: Mapping[str, Any]) -> str | None:
    for field in ("packaging_status_decision", "lease_status_decision", "status"):
        value = payload.get(field)
        if isinstance(value, str):
            return value
    return None


def _is_typed_unavailable_payload(payload: Mapping[str, Any]) -> bool:
    decision_value = _decision_value(payload)
    if decision_value not in UNAVAILABLE_DECISION_VALUES:
        return False

    has_unavailable_type = bool(payload.get("unavailable_kind") or payload.get("check_id"))
    has_reason = bool(payload.get("reason_code") or payload.get("failed_check_ids"))
    has_outcome = bool(payload.get("runner_outcome") or payload.get("provider_comment"))
    has_fault_domain = bool(payload.get("fault_domain") or payload.get("category"))
    return has_unavailable_type and has_reason and has_outcome and has_fault_domain


def measure_typed_availability_ux_metrics(
    *,
    expected_surfaces: Sequence[str],
    surface_payloads: Mapping[str, object],
    unsupported_claim_count: int = 0,
) -> dict[str, Any]:
    """Measure UX-FS-03 typed availability coverage across unavailable surfaces."""

    expected = tuple(expected_surfaces)
    missing_surfaces: list[str] = []
    vague_surfaces: list[str] = []
    typed_surfaces: list[str] = []

    for surface in expected:
        payload = _as_mapping(surface_payloads.get(surface))
        if not payload:
            missing_surfaces.append(surface)
            continue
        if _is_typed_unavailable_payload(payload):
            typed_surfaces.append(surface)
        else:
            vague_surfaces.append(surface)

    if expected:
        typed_unavailable_coverage: float | str = len(typed_surfaces) / len(expected)
    else:
        typed_unavailable_coverage = "not_applicable"

    decision = (
        "green_passed"
        if (
            typed_unavailable_coverage == 1.0
            and unsupported_claim_count == 0
            and not missing_surfaces
            and not vague_surfaces
        )
        else "red_captured"
    )

    return {
        "surface_id": "UX-FS-03",
        "typed_unavailable_coverage": typed_unavailable_coverage,
        "unsupported_claim_count": int(unsupported_claim_count),
        "expected_surface_count": len(expected),
        "typed_surface_count": len(typed_surfaces),
        "missing_surface_count": len(missing_surfaces),
        "vague_fallback_count": len(vague_surfaces),
        "typed_surfaces": typed_surfaces,
        "missing_surfaces": missing_surfaces,
        "vague_surfaces": vague_surfaces,
        "decision": decision,
    }
