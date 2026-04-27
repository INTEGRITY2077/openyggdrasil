from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "hermes_profile_acquisition_manifest.v1.schema.json"

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
def load_hermes_profile_acquisition_manifest_schema() -> dict[str, Any]:
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


def _safe_refs(values: Sequence[str] | None, *, field_name: str) -> list[str]:
    refs = [_assert_safe_ref(value, field_name=field_name) for value in values or []]
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field_name} must be unique")
    return refs


def _profile_fingerprint(profile_path: Path) -> str:
    digest = sha256()
    digest.update(b"hermes-profile-acquisition.v1\0")
    for item in sorted(profile_path.rglob("*")):
        if not item.is_file():
            continue
        try:
            relative = item.relative_to(profile_path).as_posix()
        except ValueError:
            continue
        _assert_no_forbidden_marker(relative, field_name="profile_relative_path")
        stat = item.stat()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _profile_kind(profile_path: Path) -> str:
    return "profile_directory" if profile_path.is_dir() else "profile_bundle"


def build_hermes_profile_acquisition_manifest(
    *,
    run_id: str,
    profile_id: str = "yggdrasilfgpoc",
    profile_path: str | Path,
    safe_evidence_refs: Sequence[str] | None = None,
    manifest_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Build a public-safe Hermes profile manifest without copying profile data."""

    path = Path(profile_path)
    if not path.exists():
        payload = {
            "schema_version": "hermes_profile_acquisition_manifest.v1",
            "manifest_id": manifest_id or f"hermes-profile-acquisition-{uuid.uuid4().hex}",
            "run_id": str(run_id),
            "provider_name": "hermes",
            "profile_id": str(profile_id),
            "profile_available": False,
            "profile_status": "typed_unavailable",
            "profile_ref": None,
            "profile_kind": "typed_unavailable",
            "profile_fingerprint": None,
            "safe_evidence_refs": [],
            "raw_transcript_included": False,
            "credential_ref_included": False,
            "local_path_included": False,
            "may_start_foreground_smoke": False,
            "may_claim_live_ready": False,
            "may_claim_91_percent_readiness": False,
            "claim_scope": "hermes_profile_acquisition_only",
            "rerun_condition": "provide_yggdrasilfgpoc_profile_ref",
            "reason_codes": ["hermes_profile_not_found"],
            "checked_at": checked_at or utc_now_iso(),
        }
        validate_hermes_profile_acquisition_manifest(payload)
        return payload

    payload = {
        "schema_version": "hermes_profile_acquisition_manifest.v1",
        "manifest_id": manifest_id or f"hermes-profile-acquisition-{uuid.uuid4().hex}",
        "run_id": str(run_id),
        "provider_name": "hermes",
        "profile_id": str(profile_id),
        "profile_available": True,
        "profile_status": "present",
        "profile_ref": f"hermes-profile://{profile_id}",
        "profile_kind": _profile_kind(path),
        "profile_fingerprint": _profile_fingerprint(path),
        "safe_evidence_refs": _safe_refs(safe_evidence_refs, field_name="safe_evidence_refs"),
        "raw_transcript_included": False,
        "credential_ref_included": False,
        "local_path_included": False,
        "may_start_foreground_smoke": False,
        "may_claim_live_ready": False,
        "may_claim_91_percent_readiness": False,
        "claim_scope": "hermes_profile_acquisition_only",
        "rerun_condition": None,
        "reason_codes": ["hermes_profile_present"],
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_hermes_profile_acquisition_manifest(payload)
    return payload


def validate_hermes_profile_acquisition_manifest(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_profile_acquisition_manifest_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("credential_ref_included") is not False:
        raise ValueError("credential_ref_included must be false")
    if payload.get("local_path_included") is not False:
        raise ValueError("local_path_included must be false")
    if payload.get("may_start_foreground_smoke") is not False:
        raise ValueError("profile manifest cannot authorize foreground smoke")
    if payload.get("may_claim_live_ready") is not False:
        raise ValueError("profile manifest cannot claim live readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("profile manifest cannot claim 91 percent readiness")
    if payload.get("profile_ref") is not None:
        _assert_safe_ref(payload.get("profile_ref"), field_name="profile_ref")
    _safe_refs(payload.get("safe_evidence_refs") or [], field_name="safe_evidence_refs")
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")

    available = payload.get("profile_available") is True
    if available:
        if payload.get("profile_status") != "present":
            raise ValueError("available profile must have profile_status=present")
        if not payload.get("profile_ref"):
            raise ValueError("available profile requires profile_ref")
        if not payload.get("profile_fingerprint"):
            raise ValueError("available profile requires profile_fingerprint")
        if payload.get("rerun_condition") is not None:
            raise ValueError("available profile must not carry rerun_condition")
    else:
        if payload.get("profile_status") != "typed_unavailable":
            raise ValueError("unavailable profile must be typed_unavailable")
        if payload.get("profile_ref") is not None:
            raise ValueError("unavailable profile must not carry profile_ref")
        if payload.get("profile_fingerprint") is not None:
            raise ValueError("unavailable profile must not carry profile_fingerprint")
        if payload.get("rerun_condition") != "provide_yggdrasilfgpoc_profile_ref":
            raise ValueError("unavailable profile requires provide_yggdrasilfgpoc_profile_ref")
