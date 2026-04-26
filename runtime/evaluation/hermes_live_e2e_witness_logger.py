from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from common.jsonl_io import append_jsonl
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "hermes_live_e2e_witness_event.v1.schema.json"

REQUIRED_LIVE_ROLES = {
    "hermes_run_json",
    "hermes_verdict_json",
    "e2e1_session_artifact",
    "e2e2_knowledge_delta",
    "e2e3_graphify_snapshot",
    "e2e4_mailbox_consumption",
}
FIXTURE_SOURCE_KINDS = {"contract_fixture", "derived_safe_fixture"}
LIVE_SOURCE_KINDS = {"runtime_output", "hermes_run_artifact"}
EVIDENCE_REQUIREMENTS = {
    "live_hermes_process_witness": "live_hermes_process_witness_ref_non_empty",
    "same_run_artifact_chain": "same_run_artifact_hash_chain_non_empty",
    "stale_decoy_probe": "stale_decoy_probe_ref_non_empty",
    "reasoning_lease_isolation": "reasoning_lease_isolation_ref_non_empty",
}


@lru_cache(maxsize=1)
def load_hermes_live_e2e_witness_event_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _ref_path(ref: str, *, artifact_root: Path) -> Path:
    path_part = str(ref).split("#", 1)[0].replace("\\", "/")
    return artifact_root / path_part


def _relative_ref(path: Path, *, artifact_root: Path) -> str:
    try:
        return path.resolve().relative_to(artifact_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _typed_surfaces(payload: Mapping[str, Any]) -> set[str]:
    return {
        str(item).strip()
        for item in payload.get("typed_unavailable_surfaces") or []
        if str(item).strip()
    }


def _evidence_set(payload: Mapping[str, Any]) -> set[str]:
    return {str(item).strip() for item in payload.get("evidence_required") or [] if str(item).strip()}


def _artifact_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in payload.get("artifact_chain") or [] if isinstance(row, Mapping)]


def _artifact_roles(payload: Mapping[str, Any]) -> set[str]:
    return {str(row.get("artifact_role") or "") for row in _artifact_rows(payload)}


def _verify_artifact_hashes(payload: Mapping[str, Any], *, artifact_root: Path | None) -> None:
    if artifact_root is None:
        return
    for row in _artifact_rows(payload):
        ref = str(row.get("ref") or "")
        expected = str(row.get("sha256") or "")
        path = _ref_path(ref, artifact_root=artifact_root)
        if not path.exists():
            raise ValueError(f"artifact ref does not exist for sha256 verification: {ref}")
        actual = file_sha256(path)
        if actual != expected:
            raise ValueError(f"artifact sha256 mismatch for {ref}: expected {expected}, got {actual}")


def _require_no_raw_transcript(payload: Mapping[str, Any]) -> None:
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("raw_transcript_path") is not None:
        raise ValueError("raw_transcript_path must be null")
    for row in _artifact_rows(payload):
        if row.get("contains_raw_transcript") is not False:
            raise ValueError("artifact_chain rows must not contain raw transcript")


def _require_process_live(payload: Mapping[str, Any]) -> None:
    process = payload.get("session_process")
    if not isinstance(process, Mapping):
        raise ValueError("live-equivalent witness requires session_process")
    if "hermes" not in str(process.get("command") or "").lower():
        raise ValueError("live-equivalent session_process.command must invoke hermes")
    if process.get("exit_code") != 0:
        raise ValueError("live-equivalent session_process.exit_code must be 0")
    if process.get("process_id") is None:
        raise ValueError("live-equivalent session_process.process_id is required")
    if process.get("session_id_from_provider") != payload.get("provider_session_id"):
        raise ValueError("session_process.session_id_from_provider must match provider_session_id")
    if not process.get("started_at") or not process.get("finished_at"):
        raise ValueError("live-equivalent session_process requires started_at and finished_at")


def _require_stale_decoy_probe(payload: Mapping[str, Any]) -> None:
    probe = payload.get("stale_decoy_probe")
    if not isinstance(probe, Mapping):
        raise ValueError("stale_decoy_probe is required")
    required_flags = (
        "stale_memory_injected",
        "decoy_memory_injected",
        "stale_memory_rejected",
        "decoy_memory_rejected",
    )
    missing = [flag for flag in required_flags if probe.get(flag) is not True]
    if missing:
        raise ValueError(f"stale_decoy_probe must prove: {', '.join(missing)}")
    if not probe.get("rejection_reason_refs"):
        raise ValueError("stale_decoy_probe requires rejection_reason_refs")


def _require_later_lane_boundary(payload: Mapping[str, Any]) -> None:
    typed = _typed_surfaces(payload)
    if "reasoning_lease_isolation" not in typed:
        raise ValueError("typed_unavailable_surfaces must include reasoning_lease_isolation")
    evidence = _evidence_set(payload)
    if EVIDENCE_REQUIREMENTS["reasoning_lease_isolation"] not in evidence:
        raise ValueError("missing evidence_required entry: reasoning_lease_isolation_ref_non_empty")


def _require_live_equivalent_rules(payload: Mapping[str, Any]) -> None:
    if payload.get("foreground_equivalent_only") is True or payload.get("execution_kind") == "foreground_equivalent":
        raise ValueError("foreground_equivalent evidence cannot be live-equivalent")
    if payload.get("execution_kind") != "physical_live_hermes_session":
        raise ValueError("live-equivalent witness requires execution_kind=physical_live_hermes_session")
    if payload.get("fixture_only_artifacts_present") is True:
        raise ValueError("fixture_only_artifacts_present must be false for live-equivalent witness")
    if payload.get("artifact_hashes_verified") is not True:
        raise ValueError("live-equivalent witness requires artifact_hashes_verified=true")
    if payload.get("claim_scope") != "hermes_live_witness_ready_for_e2e5":
        raise ValueError("live-equivalent witness requires claim_scope=hermes_live_witness_ready_for_e2e5")
    if payload.get("readiness_state") != "ready_for_e2e5":
        raise ValueError("live-equivalent witness requires readiness_state=ready_for_e2e5")
    if payload.get("blocking_gaps"):
        raise ValueError("live-equivalent witness must have no blocking_gaps")
    if int(payload.get("safe_evidence_pointer_count") or 0) < 8:
        raise ValueError("live-equivalent witness requires safe_evidence_pointer_count >= 8")
    if not REQUIRED_LIVE_ROLES.issubset(_artifact_roles(payload)):
        missing = sorted(REQUIRED_LIVE_ROLES - _artifact_roles(payload))
        raise ValueError(f"live-equivalent witness missing artifact roles: {', '.join(missing)}")

    for row in _artifact_rows(payload):
        role = str(row.get("artifact_role") or "")
        if role not in REQUIRED_LIVE_ROLES:
            continue
        if row.get("produced_by_run") is not True:
            raise ValueError(f"live-equivalent artifact must be produced_by_run: {role}")
        if row.get("source_kind") not in LIVE_SOURCE_KINDS:
            raise ValueError(f"live-equivalent artifact source_kind cannot be fixture: {role}")

    _require_process_live(payload)
    _require_stale_decoy_probe(payload)
    _require_later_lane_boundary(payload)


def _require_historical_not_live_rules(payload: Mapping[str, Any]) -> None:
    if payload.get("claim_scope") != "historical_session_witness_not_live_equivalent":
        raise ValueError("historical witness requires claim_scope=historical_session_witness_not_live_equivalent")
    if payload.get("readiness_state") != "not_ready":
        raise ValueError("historical witness must remain not_ready")
    if not payload.get("blocking_gaps"):
        raise ValueError("historical witness requires blocking_gaps")
    if payload.get("fixture_only_artifacts_present") is not True:
        raise ValueError("historical witness must expose fixture_only_artifacts_present")
    if "same_run_artifact_chain" not in _typed_surfaces(payload):
        raise ValueError("historical witness typed_unavailable_surfaces must include same_run_artifact_chain")


def _require_typed_unavailable_rules(payload: Mapping[str, Any]) -> None:
    if payload.get("execution_kind") != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable witness requires execution_kind=typed_unavailable_not_live_proven")
    if payload.get("session_process") is not None:
        raise ValueError("typed unavailable witness must not carry session_process")
    if payload.get("artifact_chain"):
        raise ValueError("typed unavailable witness must not carry artifact_chain")
    if payload.get("artifact_hashes_verified") is not False:
        raise ValueError("typed unavailable witness artifact_hashes_verified must be false")
    if payload.get("claim_scope") != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable witness claim_scope must be typed_unavailable_not_live_proven")
    if payload.get("readiness_state") != "not_ready":
        raise ValueError("typed unavailable witness readiness_state must be not_ready")
    if payload.get("rerun_condition") != "provide_live_hermes_e2e_witness":
        raise ValueError("typed unavailable witness rerun_condition must be provide_live_hermes_e2e_witness")

    required = {"live_hermes_process_witness", "same_run_artifact_chain", "reasoning_lease_isolation"}
    missing = sorted(required - _typed_surfaces(payload))
    if missing:
        raise ValueError(f"typed_unavailable_surfaces must include: {', '.join(missing)}")


def validate_hermes_live_e2e_witness_event(
    payload: Mapping[str, Any],
    *,
    artifact_root: Path | None = None,
) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_live_e2e_witness_event_schema(),
    )
    _require_no_raw_transcript(payload)
    _verify_artifact_hashes(payload, artifact_root=artifact_root)

    decision = str(payload.get("decision") or "")
    if decision == "live_equivalent_ready_for_e2e5":
        _require_live_equivalent_rules(payload)
    elif decision == "historical_session_witness_not_live_equivalent":
        _require_historical_not_live_rules(payload)
    elif decision == "typed_unavailable_not_live_proven":
        _require_typed_unavailable_rules(payload)
    else:
        raise ValueError(f"unknown Hermes live E2E witness decision: {decision}")


def _artifact_entry(
    *,
    role: str,
    path: Path,
    artifact_root: Path,
    source_kind: str,
) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "ref": _relative_ref(path, artifact_root=artifact_root),
        "sha256": file_sha256(path),
        "source_kind": source_kind,
        "produced_by_run": True,
        "contains_raw_transcript": False,
    }


def build_hermes_live_e2e_witness_event(
    *,
    witness_id: str,
    run_id: str,
    provider_profile: str,
    provider_session_id: str,
    session_process: Mapping[str, Any],
    artifact_paths: Mapping[str, Path],
    artifact_root: Path,
    stale_decoy_probe: Mapping[str, Any],
    safe_evidence_pointer_count: int,
    checked_at: str | None = None,
) -> dict[str, Any]:
    root = artifact_root.resolve()
    artifact_chain = [
        _artifact_entry(
            role=role,
            path=Path(artifact_paths[role]),
            artifact_root=root,
            source_kind="hermes_run_artifact" if role.startswith("hermes_") else "runtime_output",
        )
        for role in sorted(REQUIRED_LIVE_ROLES)
    ]
    payload = {
        "schema_version": "hermes_live_e2e_witness_event.v1",
        "witness_id": str(witness_id),
        "run_id": str(run_id),
        "provider_name": "hermes",
        "provider_profile": str(provider_profile),
        "provider_session_id": str(provider_session_id),
        "execution_kind": "physical_live_hermes_session",
        "witness_scope": "e2e1_to_e2e4_live_equivalence",
        "session_process": dict(session_process),
        "artifact_chain": artifact_chain,
        "stale_decoy_probe": dict(stale_decoy_probe),
        "artifact_hashes_verified": True,
        "fixture_only_artifacts_present": False,
        "foreground_equivalent_only": False,
        "raw_transcript_included": False,
        "raw_transcript_path": None,
        "safe_evidence_pointer_count": int(safe_evidence_pointer_count),
        "typed_unavailable_surfaces": ["reasoning_lease_isolation"],
        "rerun_condition": "provide_reasoning_lease_isolation_artifacts",
        "evidence_required": [EVIDENCE_REQUIREMENTS["reasoning_lease_isolation"]],
        "claim_scope": "hermes_live_witness_ready_for_e2e5",
        "decision": "live_equivalent_ready_for_e2e5",
        "readiness_state": "ready_for_e2e5",
        "blocking_gaps": [],
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_hermes_live_e2e_witness_event(payload, artifact_root=root)
    return payload


def build_typed_unavailable_hermes_live_e2e_witness_event(
    *,
    witness_id: str,
    run_id: str,
    provider_profile: str,
    reason_code: str,
    checked_at: str | None = None,
) -> dict[str, Any]:
    surfaces = [
        "live_hermes_process_witness",
        "same_run_artifact_chain",
        "reasoning_lease_isolation",
    ]
    payload = {
        "schema_version": "hermes_live_e2e_witness_event.v1",
        "witness_id": str(witness_id),
        "run_id": str(run_id),
        "provider_name": "hermes",
        "provider_profile": str(provider_profile),
        "provider_session_id": None,
        "execution_kind": "typed_unavailable_not_live_proven",
        "witness_scope": "e2e1_to_e2e4_live_equivalence",
        "session_process": None,
        "artifact_chain": [],
        "stale_decoy_probe": {
            "stale_memory_injected": False,
            "decoy_memory_injected": False,
            "stale_memory_rejected": False,
            "decoy_memory_rejected": False,
            "rejection_reason_refs": [],
        },
        "artifact_hashes_verified": False,
        "fixture_only_artifacts_present": False,
        "foreground_equivalent_only": False,
        "raw_transcript_included": False,
        "raw_transcript_path": None,
        "safe_evidence_pointer_count": 0,
        "typed_unavailable_surfaces": surfaces,
        "rerun_condition": "provide_live_hermes_e2e_witness",
        "evidence_required": [EVIDENCE_REQUIREMENTS[surface] for surface in surfaces],
        "claim_scope": "typed_unavailable_not_live_proven",
        "decision": "typed_unavailable_not_live_proven",
        "readiness_state": "not_ready",
        "blocking_gaps": [str(reason_code)],
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_hermes_live_e2e_witness_event(payload)
    return payload


def record_hermes_live_e2e_witness_event(
    payload: Mapping[str, Any],
    *,
    path: Path,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    event = dict(payload)
    validate_hermes_live_e2e_witness_event(event, artifact_root=artifact_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(path, event)
    return event
