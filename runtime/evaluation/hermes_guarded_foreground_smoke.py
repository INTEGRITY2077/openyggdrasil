from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema

from evaluation.hermes_launcher_acquisition import (
    validate_hermes_launcher_acquisition_manifest,
)
from evaluation.hermes_profile_acquisition import (
    validate_hermes_profile_acquisition_manifest,
)
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "hermes_foreground_smoke_attempt.v1.schema.json"
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
CREDENTIAL_MARKERS = (
    "credential",
    "secret",
    "token",
    "api_key",
    "apikey",
    "password",
)


@lru_cache(maxsize=1)
def load_guarded_hermes_foreground_smoke_attempt_schema() -> dict[str, Any]:
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


def _assert_no_forbidden_marker(value: str, *, field_name: str) -> None:
    normalized = value.lower().replace("\\", "/")
    for marker in RAW_TRANSCRIPT_MARKERS:
        if marker in normalized:
            raise ValueError(f"{field_name} contains raw transcript marker: {marker}")
    for marker in CREDENTIAL_MARKERS:
        if marker in normalized:
            raise ValueError(f"{field_name} contains credential marker: {marker}")


def _assert_safe_ref(value: Any, *, field_name: str) -> str:
    if not _nonempty(value):
        raise ValueError(f"{field_name} is required")
    ref = str(value).strip()
    normalized = ref.lower().replace("\\", "/")
    _assert_no_forbidden_marker(ref, field_name=field_name)
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


def _reason_codes_for_unavailable(
    launcher_manifest: Mapping[str, Any],
    profile_manifest: Mapping[str, Any],
) -> list[str]:
    reason_codes: list[str] = []
    if launcher_manifest.get("launcher_status") != "present":
        reason_codes.append(f"launcher_manifest_{launcher_manifest.get('launcher_status')}")
    if profile_manifest.get("profile_status") != "present":
        reason_codes.append(f"profile_manifest_{profile_manifest.get('profile_status')}")
    return reason_codes or ["foreground_smoke_prerequisites_unavailable"]


def _smoke_command(provider_profile: str) -> list[str]:
    return ["hermes", "-p", str(provider_profile), "chat", "--smoke"]


def build_guarded_hermes_foreground_smoke_attempt(
    *,
    run_id: str,
    provider_profile: str,
    launcher_manifest: Mapping[str, Any],
    profile_manifest: Mapping[str, Any],
    safe_bundle_ref: str,
    command_runner: Callable[[list[str]], Mapping[str, Any]],
    attempt_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Run foreground smoke only after launcher and profile manifests are present."""

    validate_hermes_launcher_acquisition_manifest(launcher_manifest)
    validate_hermes_profile_acquisition_manifest(profile_manifest)
    safe_ref = _assert_safe_ref(safe_bundle_ref, field_name="safe_bundle_ref")
    launcher_status = str(launcher_manifest.get("launcher_status"))
    profile_status = str(profile_manifest.get("profile_status"))
    prerequisites_ready = launcher_status == "present" and profile_status == "present"

    if not prerequisites_ready:
        payload = {
            "schema_version": "hermes_foreground_smoke_attempt.v1",
            "attempt_id": attempt_id or f"hermes-foreground-smoke-{uuid.uuid4().hex}",
            "run_id": str(run_id),
            "provider_name": "hermes",
            "provider_profile": str(provider_profile),
            "launcher_manifest_status": launcher_status,
            "profile_manifest_status": profile_status,
            "safe_bundle_ref": safe_ref,
            "prerequisites_ready": False,
            "smoke_status": "typed_unavailable",
            "command": [],
            "runner_invoked": False,
            "exit_code": None,
            "safe_artifact_refs": [],
            "raw_transcript_included": False,
            "credential_ref_included": False,
            "local_path_included": False,
            "may_generate_e2e1": False,
            "may_claim_live_ready": False,
            "may_claim_91_percent_readiness": False,
            "claim_scope": "foreground_smoke_prerequisites_unavailable",
            "reason_codes": _reason_codes_for_unavailable(launcher_manifest, profile_manifest),
            "checked_at": checked_at or utc_now_iso(),
        }
        validate_guarded_hermes_foreground_smoke_attempt(payload)
        return payload

    command = _smoke_command(provider_profile)
    result = dict(command_runner(command))
    exit_code = int(result.get("exit_code"))
    safe_artifact_refs = _safe_refs(
        result.get("safe_artifact_refs") or [],
        field_name="safe_artifact_refs",
    )
    payload = {
        "schema_version": "hermes_foreground_smoke_attempt.v1",
        "attempt_id": attempt_id or f"hermes-foreground-smoke-{uuid.uuid4().hex}",
        "run_id": str(run_id),
        "provider_name": "hermes",
        "provider_profile": str(provider_profile),
        "launcher_manifest_status": launcher_status,
        "profile_manifest_status": profile_status,
        "safe_bundle_ref": safe_ref,
        "prerequisites_ready": True,
        "smoke_status": "completed" if exit_code == 0 else "failed",
        "command": command,
        "runner_invoked": True,
        "exit_code": exit_code,
        "safe_artifact_refs": safe_artifact_refs,
        "raw_transcript_included": False,
        "credential_ref_included": False,
        "local_path_included": False,
        "may_generate_e2e1": False,
        "may_claim_live_ready": False,
        "may_claim_91_percent_readiness": False,
        "claim_scope": "foreground_smoke_attempt_only",
        "reason_codes": ["foreground_smoke_attempt_only"],
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_guarded_hermes_foreground_smoke_attempt(payload)
    return payload


def validate_guarded_hermes_foreground_smoke_attempt(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_guarded_hermes_foreground_smoke_attempt_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("credential_ref_included") is not False:
        raise ValueError("credential_ref_included must be false")
    if payload.get("local_path_included") is not False:
        raise ValueError("local_path_included must be false")
    if payload.get("may_generate_e2e1") is not False:
        raise ValueError("foreground smoke cannot authorize E2E1 generation")
    if payload.get("may_claim_live_ready") is not False:
        raise ValueError("foreground smoke cannot claim live readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("foreground smoke cannot claim 91 percent readiness")
    _assert_safe_ref(payload.get("safe_bundle_ref"), field_name="safe_bundle_ref")
    _safe_refs(payload.get("safe_artifact_refs") or [], field_name="safe_artifact_refs")
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")

    smoke_status = str(payload.get("smoke_status"))
    if smoke_status == "typed_unavailable":
        if payload.get("prerequisites_ready") is not False:
            raise ValueError("typed unavailable smoke requires prerequisites_ready=false")
        if payload.get("runner_invoked") is not False:
            raise ValueError("typed unavailable smoke must not invoke runner")
        if payload.get("command"):
            raise ValueError("typed unavailable smoke must not expose command")
        if payload.get("exit_code") is not None:
            raise ValueError("typed unavailable smoke must not carry exit_code")
        if not payload.get("reason_codes"):
            raise ValueError("typed unavailable smoke requires reason_codes")
    else:
        if payload.get("prerequisites_ready") is not True:
            raise ValueError("foreground smoke attempt requires prerequisites_ready=true")
        if payload.get("runner_invoked") is not True:
            raise ValueError("foreground smoke attempt requires runner_invoked=true")
        if not payload.get("command"):
            raise ValueError("foreground smoke attempt requires command")
        if payload.get("exit_code") is None:
            raise ValueError("foreground smoke attempt requires exit_code")
