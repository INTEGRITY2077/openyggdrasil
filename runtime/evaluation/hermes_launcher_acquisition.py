from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "hermes_launcher_acquisition_manifest.v1.schema.json"

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
def load_hermes_launcher_acquisition_manifest_schema() -> dict[str, Any]:
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


def _resolve_command(
    command_resolver: Callable[[str], str | None],
    launcher_name: str,
) -> str | None:
    try:
        resolved = command_resolver(launcher_name)
    except Exception:
        return None
    return str(resolved).strip() if resolved else None


def _file_sha256(path_text: str) -> str | None:
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture_version(
    *,
    launcher_name: str,
    version_probe_runner: Callable[[list[str]], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if version_probe_runner is None:
        return {
            "version_status": "not_run",
            "version": None,
            "version_exit_code": None,
            "safe_evidence_refs": [],
            "reason_codes": ["hermes_launcher_present"],
        }

    try:
        result = dict(version_probe_runner([launcher_name, "--version"]))
    except Exception:
        return {
            "version_status": "typed_unavailable",
            "version": None,
            "version_exit_code": None,
            "safe_evidence_refs": [],
            "reason_codes": ["hermes_launcher_present", "hermes_launcher_version_probe_unavailable"],
        }

    exit_code = int(result.get("exit_code", -1))
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    safe_evidence_refs = _safe_refs(
        result.get("safe_evidence_refs") or [],
        field_name="safe_evidence_refs",
    )
    if stdout:
        _assert_no_forbidden_marker(stdout, field_name="version")
    if stderr:
        _assert_no_forbidden_marker(stderr, field_name="version_stderr")

    if exit_code == 0 and stdout:
        return {
            "version_status": "captured_safe",
            "version": stdout[:160],
            "version_exit_code": exit_code,
            "safe_evidence_refs": safe_evidence_refs,
            "reason_codes": ["hermes_launcher_present", "hermes_launcher_version_captured"],
        }
    return {
        "version_status": "failed",
        "version": None,
        "version_exit_code": exit_code,
        "safe_evidence_refs": safe_evidence_refs,
        "reason_codes": ["hermes_launcher_present", "hermes_launcher_version_probe_failed"],
    }


def build_hermes_launcher_acquisition_manifest(
    *,
    run_id: str,
    launcher_name: str = "hermes",
    command_resolver: Callable[[str], str | None],
    version_probe_runner: Callable[[list[str]], Mapping[str, Any]] | None = None,
    manifest_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Build a public-safe Hermes launcher manifest.

    The resolved executable path is used only locally for hashing. The payload
    exposes a stable tool ref instead of a local filesystem path.
    """

    resolved = _resolve_command(command_resolver, launcher_name)
    if not resolved:
        payload = {
            "schema_version": "hermes_launcher_acquisition_manifest.v1",
            "manifest_id": manifest_id or f"hermes-launcher-acquisition-{uuid.uuid4().hex}",
            "run_id": str(run_id),
            "provider_name": "hermes",
            "launcher_name": str(launcher_name),
            "launcher_available": False,
            "launcher_status": "typed_unavailable",
            "launcher_ref": None,
            "launcher_sha256": None,
            "version_status": "not_run",
            "version": None,
            "version_exit_code": None,
            "safe_evidence_refs": [],
            "raw_transcript_included": False,
            "credential_ref_included": False,
            "local_path_included": False,
            "may_start_foreground_smoke": False,
            "may_claim_live_ready": False,
            "may_claim_91_percent_readiness": False,
            "claim_scope": "hermes_launcher_acquisition_only",
            "rerun_condition": "provide_hermes_launcher_ref",
            "reason_codes": ["hermes_launcher_not_found"],
            "checked_at": checked_at or utc_now_iso(),
        }
        validate_hermes_launcher_acquisition_manifest(payload)
        return payload

    version_capture = _capture_version(
        launcher_name=launcher_name,
        version_probe_runner=version_probe_runner,
    )
    payload = {
        "schema_version": "hermes_launcher_acquisition_manifest.v1",
        "manifest_id": manifest_id or f"hermes-launcher-acquisition-{uuid.uuid4().hex}",
        "run_id": str(run_id),
        "provider_name": "hermes",
        "launcher_name": str(launcher_name),
        "launcher_available": True,
        "launcher_status": "present",
        "launcher_ref": f"env-tool://{launcher_name}",
        "launcher_sha256": _file_sha256(resolved),
        "version_status": version_capture["version_status"],
        "version": version_capture["version"],
        "version_exit_code": version_capture["version_exit_code"],
        "safe_evidence_refs": version_capture["safe_evidence_refs"],
        "raw_transcript_included": False,
        "credential_ref_included": False,
        "local_path_included": False,
        "may_start_foreground_smoke": False,
        "may_claim_live_ready": False,
        "may_claim_91_percent_readiness": False,
        "claim_scope": "hermes_launcher_acquisition_only",
        "rerun_condition": None,
        "reason_codes": version_capture["reason_codes"],
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_hermes_launcher_acquisition_manifest(payload)
    return payload


def validate_hermes_launcher_acquisition_manifest(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_launcher_acquisition_manifest_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("credential_ref_included") is not False:
        raise ValueError("credential_ref_included must be false")
    if payload.get("local_path_included") is not False:
        raise ValueError("local_path_included must be false")
    if payload.get("may_start_foreground_smoke") is not False:
        raise ValueError("launcher manifest cannot authorize foreground smoke")
    if payload.get("may_claim_live_ready") is not False:
        raise ValueError("launcher manifest cannot claim live readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("launcher manifest cannot claim 91 percent readiness")
    if payload.get("launcher_ref") is not None:
        _assert_safe_ref(payload.get("launcher_ref"), field_name="launcher_ref")
    _safe_refs(payload.get("safe_evidence_refs") or [], field_name="safe_evidence_refs")
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")

    available = payload.get("launcher_available") is True
    if available:
        if payload.get("launcher_status") != "present":
            raise ValueError("available launcher must have launcher_status=present")
        if not payload.get("launcher_ref"):
            raise ValueError("available launcher requires launcher_ref")
        if payload.get("rerun_condition") is not None:
            raise ValueError("available launcher must not carry rerun_condition")
    else:
        if payload.get("launcher_status") != "typed_unavailable":
            raise ValueError("unavailable launcher must be typed_unavailable")
        if payload.get("launcher_ref") is not None:
            raise ValueError("unavailable launcher must not carry launcher_ref")
        if payload.get("launcher_sha256") is not None:
            raise ValueError("unavailable launcher must not carry launcher_sha256")
        if payload.get("rerun_condition") != "provide_hermes_launcher_ref":
            raise ValueError("unavailable launcher requires provide_hermes_launcher_ref")
