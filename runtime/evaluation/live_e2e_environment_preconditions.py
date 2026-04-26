from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema

from evaluation.live_e2e_readiness_gate import (
    REQUIRED_PRECONDITIONS,
    build_live_e2e_readiness_gate,
)
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "live_e2e_environment_preconditions.v1.schema.json"
READINESS_GATE_SCHEMA_PATH = CONTRACTS_ROOT / "live_e2e_readiness_gate.v1.schema.json"


@lru_cache(maxsize=1)
def load_live_e2e_environment_preconditions_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _assert_timestamp(value: Any, *, field_name: str) -> str:
    if not _nonempty(value):
        raise ValueError(f"{field_name} is required")
    timestamp = str(value).strip()
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO 8601") from exc
    return timestamp


def _present_precondition(
    precondition_id: str,
    *,
    source_kind: str,
    artifact_ref: str,
    safe_evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    refs = safe_evidence_refs if safe_evidence_refs is not None else [artifact_ref]
    return {
        "precondition_id": precondition_id,
        "status": "present",
        "source_kind": source_kind,
        "artifact_ref": artifact_ref,
        "reason_code": None,
        "safe_evidence_refs": refs,
        "contains_raw_transcript": False,
    }


def _typed_unavailable_precondition(
    precondition_id: str,
    *,
    reason_code: str,
) -> dict[str, Any]:
    return {
        "precondition_id": precondition_id,
        "status": "typed_unavailable",
        "source_kind": "typed_unavailable",
        "artifact_ref": None,
        "reason_code": reason_code,
        "safe_evidence_refs": [],
        "contains_raw_transcript": False,
    }


def _default_profile_path(provider_profile: str) -> Path:
    home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    if provider_profile == "default":
        return home / ".hermes"
    return home / ".hermes" / "profiles" / provider_profile


def _resolve_command(
    command_resolver: Callable[[str], str | None],
    command_name: str,
) -> str | None:
    try:
        resolved = command_resolver(command_name)
    except Exception:
        return None
    return str(resolved).strip() if resolved else None


def _probe_wsl_tools(wsl_distro: str) -> dict[str, bool]:
    command = "command -v bwrap >/dev/null 2>&1 && command -v socat >/dev/null 2>&1"
    try:
        completed = subprocess.run(
            ["wsl", "-d", wsl_distro, "--", "bash", "-lc", command],
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return {"bwrap": False, "socat": False}
    available = completed.returncode == 0
    return {"bwrap": available, "socat": available}


def _precondition_summary(preconditions: list[Mapping[str, Any]]) -> dict[str, Any]:
    satisfied = [
        item["precondition_id"]
        for item in preconditions
        if item.get("status") == "present"
    ]
    missing = [
        item["precondition_id"]
        for item in preconditions
        if item.get("status") == "missing"
    ]
    typed_unavailable = [
        item["precondition_id"]
        for item in preconditions
        if item.get("status") == "typed_unavailable"
    ]
    invalid = [
        item["precondition_id"]
        for item in preconditions
        if item.get("status") == "invalid"
    ]
    ready = (
        len(satisfied) == len(REQUIRED_PRECONDITIONS)
        and not missing
        and not typed_unavailable
        and not invalid
    )
    reason_codes = ["live_ready_claim_deferred_to_report_gate"]
    reason_codes.extend(f"precondition_missing_{item}" for item in missing)
    reason_codes.extend(f"precondition_typed_unavailable_{item}" for item in typed_unavailable)
    reason_codes.extend(f"precondition_invalid_{item}" for item in invalid)
    return {
        "required_precondition_ids": list(REQUIRED_PRECONDITIONS),
        "satisfied_precondition_ids": satisfied,
        "missing_precondition_ids": missing,
        "typed_unavailable_precondition_ids": typed_unavailable,
        "invalid_precondition_ids": invalid,
        "readiness_preconditions_ready": ready,
        "reason_codes": reason_codes,
    }


def build_live_e2e_environment_preconditions(
    *,
    run_lock_ref: str | None,
    artifact_root_ref: str | None,
    safe_capture_policy_ref: str | None,
    stale_decoy_probe_plan_ref: str | None,
    hermes_binary: str = "hermes",
    provider_profile: str = "yggdrasilfgpoc",
    provider_profile_path: str | Path | None = None,
    command_resolver: Callable[[str], str | None] = shutil.which,
    wsl_distro: str = "ubuntu-agent",
    wsl_tool_status: Mapping[str, bool] | None = None,
    raw_transcript_filter_enabled: bool = True,
    phase_id: str = "p9-live-e2e",
    probe_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Probe physical live E2E start preconditions for the readiness gate.

    The payload is public-safe: it returns safe refs and typed unavailable
    reasons, not local provider transcripts or private raw paths.
    """

    preconditions: list[dict[str, Any]] = []

    if run_lock_ref:
        preconditions.append(
            _present_precondition(
                "run_lock_held",
                source_kind="runtime_check",
                artifact_ref=str(run_lock_ref),
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "run_lock_held",
                reason_code="run_lock_ref_not_supplied",
            )
        )

    resolved_hermes = _resolve_command(command_resolver, hermes_binary)
    if resolved_hermes:
        preconditions.append(
            _present_precondition(
                "hermes_binary_available",
                source_kind="runtime_check",
                artifact_ref=f"env-tool://{hermes_binary}",
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "hermes_binary_available",
                reason_code="hermes_binary_not_on_path",
            )
        )

    profile_path = Path(provider_profile_path) if provider_profile_path else _default_profile_path(provider_profile)
    if profile_path.exists():
        preconditions.append(
            _present_precondition(
                "provider_profile_available",
                source_kind="runtime_check",
                artifact_ref=f"hermes-profile://{provider_profile}",
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "provider_profile_available",
                reason_code=f"hermes_profile_{provider_profile}_missing",
            )
        )

    if artifact_root_ref:
        preconditions.append(
            _present_precondition(
                "live_artifact_root_available",
                source_kind="operator_declared",
                artifact_ref=str(artifact_root_ref),
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "live_artifact_root_available",
                reason_code="live_artifact_root_ref_not_supplied",
            )
        )

    if safe_capture_policy_ref:
        preconditions.append(
            _present_precondition(
                "safe_capture_policy_available",
                source_kind="contract_surface",
                artifact_ref=str(safe_capture_policy_ref),
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "safe_capture_policy_available",
                reason_code="safe_capture_policy_ref_not_supplied",
            )
        )

    if raw_transcript_filter_enabled:
        preconditions.append(
            _present_precondition(
                "raw_transcript_filter_enabled",
                source_kind="contract_surface",
                artifact_ref="public-contract://openyggdrasil/contracts/live_e2e_readiness_gate.v1.schema.json#raw-transcript-filter-policy",
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "raw_transcript_filter_enabled",
                reason_code="raw_transcript_filter_disabled",
            )
        )

    if stale_decoy_probe_plan_ref:
        preconditions.append(
            _present_precondition(
                "stale_decoy_probe_plan_available",
                source_kind="contract_surface",
                artifact_ref=str(stale_decoy_probe_plan_ref),
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "stale_decoy_probe_plan_available",
                reason_code="stale_decoy_probe_plan_ref_not_supplied",
            )
        )

    wsl_status = dict(wsl_tool_status) if wsl_tool_status is not None else _probe_wsl_tools(wsl_distro)
    if wsl_status.get("bwrap") is True and wsl_status.get("socat") is True:
        preconditions.append(
            _present_precondition(
                "wsl2_bubblewrap_available",
                source_kind="runtime_check",
                artifact_ref=f"wsl2://{wsl_distro}/usr/bin/bwrap",
                safe_evidence_refs=[
                    f"wsl2://{wsl_distro}/usr/bin/bwrap",
                    f"wsl2://{wsl_distro}/usr/bin/socat",
                ],
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "wsl2_bubblewrap_available",
                reason_code="wsl2_bubblewrap_or_socat_unavailable",
            )
        )

    if SCHEMA_PATH.exists() and READINESS_GATE_SCHEMA_PATH.exists():
        preconditions.append(
            _present_precondition(
                "schema_contracts_available",
                source_kind="contract_surface",
                artifact_ref="public-contract://openyggdrasil/contracts/live_e2e_environment_preconditions.v1.schema.json",
                safe_evidence_refs=[
                    "public-contract://openyggdrasil/contracts/live_e2e_environment_preconditions.v1.schema.json",
                    "public-contract://openyggdrasil/contracts/live_e2e_readiness_gate.v1.schema.json",
                ],
            )
        )
    else:
        preconditions.append(
            _typed_unavailable_precondition(
                "schema_contracts_available",
                reason_code="live_e2e_schema_contract_missing",
            )
        )

    payload = {
        "schema_version": "live_e2e_environment_preconditions.v1",
        "probe_id": probe_id or f"p9-live-e2e-env-{uuid.uuid4().hex}",
        "phase_id": str(phase_id),
        "precondition_scope": "p9_physical_same_run_hermes_live_e2e_environment",
        "preconditions": preconditions,
        **_precondition_summary(preconditions),
        "raw_transcript_included": False,
        "may_claim_live_ready": False,
        "may_claim_91_percent_readiness": False,
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_live_e2e_environment_preconditions(payload)
    return payload


def validate_live_e2e_environment_preconditions(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_live_e2e_environment_preconditions_schema(),
    )
    if tuple(payload.get("required_precondition_ids") or []) != REQUIRED_PRECONDITIONS:
        raise ValueError("required_precondition_ids must match the live E2E precondition set")
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("may_claim_live_ready") is not False:
        raise ValueError("environment preconditions cannot claim live readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("environment preconditions cannot claim 91 percent readiness")
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")

    gate = build_live_e2e_readiness_gate(
        preconditions=payload.get("preconditions") or [],
        evidence_lanes=[],
        checked_at=str(payload["checked_at"]),
    )
    expected = {
        "satisfied_precondition_ids": gate["satisfied_precondition_ids"],
        "missing_precondition_ids": gate["missing_precondition_ids"],
        "typed_unavailable_precondition_ids": gate["typed_unavailable_precondition_ids"],
        "invalid_precondition_ids": gate["invalid_precondition_ids"],
        "readiness_preconditions_ready": gate["may_start_physical_live_probe"],
    }
    for field_name, expected_value in expected.items():
        if payload.get(field_name) != expected_value:
            raise ValueError(f"{field_name} does not match readiness gate interpretation")
