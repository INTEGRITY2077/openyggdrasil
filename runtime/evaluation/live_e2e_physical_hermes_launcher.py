from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema

from evaluation.live_e2e_environment_preconditions import (
    validate_live_e2e_environment_preconditions,
)
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "live_e2e_physical_hermes_launch_attempt.v1.schema.json"
RAW_TRANSCRIPT_MARKERS = (
    "raw-transcript",
    "raw_transcript",
    "raw provider transcript",
    "raw_provider_transcript",
    "raw-provider-session",
    "raw_provider_session",
    "provider-session-copy",
    "provider_session_copy",
    "transcript.txt",
    "transcripts/",
)


@lru_cache(maxsize=1)
def load_physical_hermes_launch_attempt_schema() -> dict[str, Any]:
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


def _assert_no_raw_transcript_marker(value: str, *, field_name: str) -> None:
    normalized = value.lower().replace("\\", "/")
    for marker in RAW_TRANSCRIPT_MARKERS:
        if marker in normalized:
            raise ValueError(f"{field_name} contains raw transcript marker: {marker}")


def _assert_safe_ref(value: Any, *, field_name: str) -> str:
    if not _nonempty(value):
        raise ValueError(f"{field_name} is required")
    ref = str(value).strip()
    normalized = ref.lower().replace("\\", "/")
    _assert_no_raw_transcript_marker(ref, field_name=field_name)
    if re.match(r"^[a-z]:/", normalized) or normalized.startswith(("/", "file://")):
        raise ValueError(f"{field_name} must be an evidence ref, not a local path")
    if "://" not in ref:
        raise ValueError(f"{field_name} must use an explicit evidence ref scheme")
    return ref


def _safe_refs(values: Any, *, field_name: str) -> list[str]:
    refs = [_assert_safe_ref(value, field_name=field_name) for value in values or []]
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field_name} must be unique")
    return refs


def _hermes_command(provider_profile: str) -> list[str]:
    return ["hermes", "-p", str(provider_profile), "chat", "--pass-session-id"]


def _preflight_reason_codes(preconditions: Mapping[str, Any]) -> list[str]:
    return [str(item) for item in preconditions.get("reason_codes") or [] if str(item).strip()]


def build_physical_hermes_launch_attempt(
    *,
    run_id: str,
    provider_profile: str,
    provider_session_id: str | None,
    preconditions: Mapping[str, Any],
    safe_bundle_ref: str,
    command_runner: Callable[[list[str]], Mapping[str, Any]],
    attempt_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Run or block the physical Hermes launch according to preflight gates."""

    validate_live_e2e_environment_preconditions(preconditions)
    safe_ref = _assert_safe_ref(safe_bundle_ref, field_name="safe_bundle_ref")
    preconditions_ready = preconditions.get("readiness_preconditions_ready") is True
    command = _hermes_command(provider_profile)

    if not preconditions_ready:
        payload = {
            "schema_version": "live_e2e_physical_hermes_launch_attempt.v1",
            "attempt_id": attempt_id or f"p9-physical-hermes-launch-{uuid.uuid4().hex}",
            "run_id": str(run_id),
            "provider_name": "hermes",
            "provider_profile": str(provider_profile),
            "provider_session_id": provider_session_id,
            "safe_bundle_ref": safe_ref,
            "precondition_probe_id": str(preconditions.get("probe_id") or ""),
            "preconditions_ready": False,
            "launcher_decision": "typed_unavailable_not_started",
            "command": [],
            "runner_invoked": False,
            "exit_code": None,
            "safe_artifact_refs": [],
            "raw_transcript_included": False,
            "may_claim_live_ready": False,
            "may_claim_91_percent_readiness": False,
            "claim_scope": "preflight_blocked_no_physical_execution",
            "reason_codes": _preflight_reason_codes(preconditions),
            "checked_at": checked_at or utc_now_iso(),
        }
        validate_physical_hermes_launch_attempt(payload)
        return payload

    result = dict(command_runner(command))
    exit_code = int(result.get("exit_code"))
    safe_artifact_refs = _safe_refs(
        result.get("safe_artifact_refs") or [],
        field_name="safe_artifact_refs",
    )
    payload = {
        "schema_version": "live_e2e_physical_hermes_launch_attempt.v1",
        "attempt_id": attempt_id or f"p9-physical-hermes-launch-{uuid.uuid4().hex}",
        "run_id": str(run_id),
        "provider_name": "hermes",
        "provider_profile": str(provider_profile),
        "provider_session_id": result.get("provider_session_id") or provider_session_id,
        "safe_bundle_ref": safe_ref,
        "precondition_probe_id": str(preconditions.get("probe_id") or ""),
        "preconditions_ready": True,
        "launcher_decision": (
            "physical_hermes_process_completed"
            if exit_code == 0
            else "physical_hermes_process_failed"
        ),
        "command": command,
        "runner_invoked": True,
        "exit_code": exit_code,
        "safe_artifact_refs": safe_artifact_refs,
        "raw_transcript_included": False,
        "may_claim_live_ready": False,
        "may_claim_91_percent_readiness": False,
        "claim_scope": "physical_launcher_attempt_only",
        "reason_codes": ["physical_launcher_attempt_only"],
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_physical_hermes_launch_attempt(payload)
    return payload


def validate_physical_hermes_launch_attempt(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_physical_hermes_launch_attempt_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("may_claim_live_ready") is not False:
        raise ValueError("launch attempt cannot claim live readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("launch attempt cannot claim 91 percent readiness")
    _assert_safe_ref(payload.get("safe_bundle_ref"), field_name="safe_bundle_ref")
    _safe_refs(payload.get("safe_artifact_refs") or [], field_name="safe_artifact_refs")
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")

    decision = str(payload.get("launcher_decision") or "")
    if decision == "typed_unavailable_not_started":
        if payload.get("preconditions_ready") is not False:
            raise ValueError("typed unavailable launcher must have preconditions_ready=false")
        if payload.get("runner_invoked") is not False:
            raise ValueError("typed unavailable launcher must not invoke runner")
        if payload.get("command"):
            raise ValueError("typed unavailable launcher must not expose execution command")
        if payload.get("exit_code") is not None:
            raise ValueError("typed unavailable launcher must not carry exit_code")
        if not payload.get("reason_codes"):
            raise ValueError("typed unavailable launcher requires reason_codes")
    else:
        if payload.get("preconditions_ready") is not True:
            raise ValueError("physical launch attempt requires preconditions_ready=true")
        if payload.get("runner_invoked") is not True:
            raise ValueError("physical launch attempt requires runner_invoked=true")
        if not payload.get("command"):
            raise ValueError("physical launch attempt requires command")
        if payload.get("exit_code") is None:
            raise ValueError("physical launch attempt requires exit_code")
