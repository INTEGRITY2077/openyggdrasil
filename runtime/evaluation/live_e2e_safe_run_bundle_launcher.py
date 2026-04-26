from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "live_e2e_safe_run_bundle.v1.schema.json"

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
def load_safe_live_e2e_run_bundle_schema() -> dict[str, Any]:
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


def _safe_capture_refs(values: Sequence[str]) -> list[str]:
    refs = [
        _assert_safe_ref(value, field_name="requested_capture_refs")
        for value in values
    ]
    if len(set(refs)) != len(refs):
        raise ValueError("requested_capture_refs must be unique")
    return refs


def build_safe_live_e2e_run_bundle(
    *,
    run_id: str,
    provider_profile: str,
    provider_session_id: str,
    artifact_root_ref: str,
    requested_capture_refs: Sequence[str] = (),
    bundle_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Build a safe, public-contract-shaped placeholder for live E2E artifacts.

    This initializes the safe artifact-root contract surface only. It never
    authorizes physical execution and never claims live readiness.
    """

    safe_root_ref = _assert_safe_ref(artifact_root_ref, field_name="artifact_root_ref")
    capture_refs = _safe_capture_refs(requested_capture_refs)
    payload = {
        "schema_version": "live_e2e_safe_run_bundle.v1",
        "bundle_id": bundle_id or f"safe-live-e2e-bundle-{uuid.uuid4().hex}",
        "run_id": str(run_id),
        "provider_name": "hermes",
        "provider_profile": str(provider_profile),
        "provider_session_id": str(provider_session_id),
        "artifact_root_ref": safe_root_ref,
        "artifact_root_initialized": True,
        "capture_refs": capture_refs,
        "capture_ref_count": len(capture_refs),
        "raw_transcript_included": False,
        "same_run_only": True,
        "may_start_physical_live_probe": False,
        "may_claim_live_ready": False,
        "may_claim_91_percent_readiness": False,
        "claim_scope": "safe_live_e2e_artifact_root_only",
        "reason_codes": ["live_execution_not_started"],
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_safe_live_e2e_run_bundle(payload)
    return payload


def validate_safe_live_e2e_run_bundle(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_safe_live_e2e_run_bundle_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("may_start_physical_live_probe") is not False:
        raise ValueError("safe run bundle cannot authorize physical live execution")
    if payload.get("may_claim_live_ready") is not False:
        raise ValueError("safe run bundle cannot claim live readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("safe run bundle cannot claim 91 percent readiness")
    if payload.get("capture_ref_count") != len(payload.get("capture_refs") or []):
        raise ValueError("capture_ref_count must match capture_refs")
    _assert_safe_ref(payload.get("artifact_root_ref"), field_name="artifact_root_ref")
    _safe_capture_refs([str(ref) for ref in payload.get("capture_refs") or []])
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")
