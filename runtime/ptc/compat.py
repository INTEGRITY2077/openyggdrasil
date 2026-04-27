"""Compatibility policy for the PTC package skeleton."""

from __future__ import annotations

CLAIM_SCOPE = "structural_readiness_only"
PACKAGE_STATUS = "skeleton_no_behavior_change"

LEGACY_IMPORT_SURFACES = (
    "retrieval.programmatic_tool_runtime",
    "retrieval.pathfinder_ptc_mvp",
    "retrieval.pathfinder",
    "pathfinder",
    "pathfinder_ptc_mvp",
)

FUTURE_PTC_MODULES = (
    "ptc.engine",
    "ptc.tool_surface",
    "ptc.result_gate",
    "ptc.trace",
    "ptc.bundle",
    "ptc.orchestration",
)


def compatibility_policy() -> dict[str, object]:
    return {
        "claim_scope": CLAIM_SCOPE,
        "package_status": PACKAGE_STATUS,
        "legacy_import_surfaces": list(LEGACY_IMPORT_SURFACES),
        "future_ptc_modules": list(FUTURE_PTC_MODULES),
        "dynamic_program_source_enabled": False,
        "live_readiness_claimed": False,
    }


__all__ = [
    "CLAIM_SCOPE",
    "FUTURE_PTC_MODULES",
    "LEGACY_IMPORT_SURFACES",
    "PACKAGE_STATUS",
    "compatibility_policy",
]
