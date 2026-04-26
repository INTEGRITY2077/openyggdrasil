from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

P6_H1_EVIDENCE_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-26\\"
    "2026-04-26_phase-6-hermes-live-foreground-bootstrap-smoke.md"
)
P6_H2_EVIDENCE_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-26\\"
    "2026-04-26_phase-6-hermes-live-foreground-memory-roundtrip.md"
)
MISSING_PROVIDER_HARNESS_PROBE_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\providers\\hermes\\projects\\harness\\"
    "hermes_foreground_probe.py"
)
P6_P1_ACTION = "P6.P1.hermes-provider-packaging-baseline"
P9_R1_ACTION = "P9.R1.live-provider-proof-or-typed-unavailable-reproof"


UNAVAILABLE_KIND_DEFINITIONS: dict[str, dict[str, str]] = {
    "provider_harness_dependency_missing": {
        "reason_code": "hermes_provider_harness_foreground_probe_missing",
        "runner_outcome": "foreground_probe_dependency_missing",
        "fault_domain": "provider_harness",
    },
    "live_foreground_surface_unavailable": {
        "reason_code": "hermes_live_foreground_surface_unavailable",
        "runner_outcome": "live_foreground_unavailable",
        "fault_domain": "provider_live_surface",
    },
    "live_foreground_bootstrap_unavailable": {
        "reason_code": "hermes_live_foreground_bootstrap_unavailable",
        "runner_outcome": "live_bootstrap_unavailable",
        "fault_domain": "provider_live_surface",
    },
    "live_foreground_memory_roundtrip_unavailable": {
        "reason_code": "hermes_live_foreground_memory_roundtrip_unavailable",
        "runner_outcome": "live_memory_roundtrip_unavailable",
        "fault_domain": "provider_live_surface",
    },
    "live_foreground_unverifiable": {
        "reason_code": "hermes_live_foreground_unverifiable",
        "runner_outcome": "live_foreground_unverifiable",
        "fault_domain": "provider_capability",
    },
}


@lru_cache(maxsize=1)
def load_hermes_foreground_unavailable_contract_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_foreground_unavailable_contract.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_foreground_unavailable_contract(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_foreground_unavailable_contract_schema(),
    )


def _fallback_path_status(fallback_policy: str) -> str:
    if fallback_policy == "foreground_equivalent_contract":
        return "foreground_equivalent_contract_available"
    if fallback_policy == "typed_known_limitation":
        return "typed_known_limitation_available"
    if fallback_policy == "manual_review":
        return "manual_review_available"
    raise ValueError(f"unknown Hermes foreground fallback policy: {fallback_policy}")


def build_hermes_foreground_unavailable_contract(
    *,
    unavailable_kind: str = "provider_harness_dependency_missing",
    provider_profile: str | None = "yggdrasilfgpoc",
    provider_session_id: str | None = None,
    reason_code: str | None = None,
    fallback_policy: str = "foreground_equivalent_contract",
    bootstrap_contract_status: str = "foreground_equivalent_passed",
    memory_roundtrip_contract_status: str = "foreground_equivalent_passed",
    missing_dependency_refs: Sequence[str] = (MISSING_PROVIDER_HARNESS_PROBE_REF,),
    evidence_refs: Sequence[str] = (P6_H1_EVIDENCE_REF, P6_H2_EVIDENCE_REF),
    next_action: str = P6_P1_ACTION,
) -> dict[str, Any]:
    """Build the Phase 6 Hermes foreground typed unavailable packaging result.

    This contract keeps the Hermes live foreground limitation visible after the
    bootstrap and memory roundtrip fallback proofs close. It is intentionally
    not a live foreground proof and it forbids relabeling foreground-equivalent
    results as provider foreground completion.
    """

    if unavailable_kind not in UNAVAILABLE_KIND_DEFINITIONS:
        raise ValueError(f"unknown Hermes foreground unavailable kind: {unavailable_kind}")
    definition = UNAVAILABLE_KIND_DEFINITIONS[unavailable_kind]
    output = {
        "schema_version": "hermes_foreground_unavailable_contract.v1",
        "unavailable_id": uuid.uuid4().hex,
        "provider_id": "hermes",
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "unavailable_kind": unavailable_kind,
        "reason_code": reason_code or definition["reason_code"],
        "packaging_status_decision": "unavailable",
        "runner_outcome": definition["runner_outcome"],
        "fault_domain": definition["fault_domain"],
        "openyggdrasil_runtime_failure": False,
        "fallback_policy": fallback_policy,
        "fallback_path_status": _fallback_path_status(fallback_policy),
        "bootstrap_contract_status": bootstrap_contract_status,
        "memory_roundtrip_contract_status": memory_roundtrip_contract_status,
        "live_foreground_claimed": False,
        "foreground_equivalent_relabel": False,
        "raw_transcript_copied": False,
        "raw_session_copied": False,
        "global_inbox_created": False,
        "doc_committed": False,
        "missing_dependency_refs": [str(ref) for ref in missing_dependency_refs][:16],
        "evidence_refs": [str(ref) for ref in evidence_refs][:32],
        "next_action": next_action,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_foreground_unavailable_contract(output)
    return output


def build_live_foreground_probe_typed_unavailable_reproof(
    *,
    live_probe_path: Path | None = None,
) -> dict[str, Any]:
    """Build the P9.R1 re-proof when the physical live probe is absent.

    P9 must keep this separate from the foreground-equivalent contract. This
    helper only proves the live-provider surface is not currently executable.
    """

    live_probe_path = live_probe_path or Path(MISSING_PROVIDER_HARNESS_PROBE_REF)
    if live_probe_path.exists():
        raise RuntimeError(
            "live foreground probe exists; run the live probe instead of emitting missing-harness reproof"
        )
    return build_hermes_foreground_unavailable_contract(
        unavailable_kind="provider_harness_dependency_missing",
        missing_dependency_refs=[str(live_probe_path)],
        next_action=P9_R1_ACTION,
    )


def measure_foreground_truth_ux_metrics(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Quantify UX-FS-02 foreground truth failure for a Hermes unavailable result."""

    typed_fields = (
        "unavailable_kind",
        "reason_code",
        "runner_outcome",
        "fault_domain",
    )
    unavailable_expected = payload.get("packaging_status_decision") == "unavailable"
    typed_unavailable_reported = unavailable_expected and all(
        bool(payload.get(field)) for field in typed_fields
    )
    foreground_equivalent_labeled_live = bool(
        payload.get("foreground_equivalent_relabel")
        or (
            payload.get("fallback_policy") == "foreground_equivalent_contract"
            and payload.get("live_foreground_claimed")
        )
    )
    live_mislabel_count = int(bool(payload.get("live_foreground_claimed"))) + int(
        foreground_equivalent_labeled_live
    )
    typed_unavailable_coverage: float | str
    if unavailable_expected:
        typed_unavailable_coverage = 1.0 if typed_unavailable_reported else 0.0
    else:
        typed_unavailable_coverage = "not_applicable"

    return {
        "surface_id": "UX-FS-02",
        "live_mislabel_count": live_mislabel_count,
        "typed_unavailable_coverage": typed_unavailable_coverage,
        "foreground_equivalent_labeled_live": foreground_equivalent_labeled_live,
        "decision": (
            "green_passed"
            if live_mislabel_count == 0 and typed_unavailable_coverage == 1.0
            else "red_captured"
        ),
    }
