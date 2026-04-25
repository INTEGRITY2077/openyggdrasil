from __future__ import annotations

import hashlib
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from attachments.provider_attachment import validate_provider_descriptor
from harness_common import utc_now_iso
from reasoning.hermes_background_invocation_smoke import (
    validate_hermes_background_invocation_smoke,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

HERMES_BACKGROUND_INVOCATION_SMOKE_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_phase-4-hermes-background-invocation-smoke.md"
)

P4_H2_ACTION = "P4.H2.hermes-background-task-id-capture"
P4_H3_ACTION = "P4.H3.hermes-background-result-contract"

BG_TASK_REF_RE = re.compile(r"\bbg_[A-Za-z0-9][A-Za-z0-9_.:-]*\b")

UNSAFE_REASON_CODES = {
    "raw_output_copied": "raw_provider_gateway_output_copy_not_allowed",
    "raw_session_copied": "raw_provider_session_copy_not_allowed",
    "state_db_result_harvested": "state_db_result_harvesting_not_allowed",
}


@lru_cache(maxsize=1)
def load_hermes_background_task_capture_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_background_task_capture.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_background_task_capture(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_background_task_capture_schema(),
    )


def extract_bg_task_ref(gateway_output_text: str) -> str | None:
    match = BG_TASK_REF_RE.search(gateway_output_text)
    return match.group(0) if match else None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _first_unsafe_reason(safety: Mapping[str, bool]) -> str | None:
    for flag_name, reason_code in UNSAFE_REASON_CODES.items():
        if safety.get(flag_name) is True:
            return reason_code
    return None


def build_hermes_background_task_capture(
    *,
    provider_descriptor: Mapping[str, Any],
    invocation_smoke: Mapping[str, Any],
    gateway_output_text: str | None,
    evidence_refs: Sequence[str] = (HERMES_BACKGROUND_INVOCATION_SMOKE_REF,),
    safety_flags: Mapping[str, bool] | None = None,
    live_provider_invoked: bool = False,
) -> dict[str, Any]:
    """Capture a Hermes bg_ task reference without storing provider raw output.

    The only retained gateway-output material is a sha256 digest and the bg_
    reference itself. This proof does not claim lease completion or result
    ingestion.
    """

    validate_provider_descriptor(provider_descriptor)
    validate_hermes_background_invocation_smoke(invocation_smoke)

    safety = {
        "raw_output_copied": False,
        "raw_session_copied": False,
        "state_db_result_harvested": False,
    }
    safety.update(dict(safety_flags or {}))
    reason_code = _first_unsafe_reason(safety)

    output_text = gateway_output_text or ""
    task_ref = extract_bg_task_ref(output_text)
    explicit_surface_ready = invocation_smoke.get("smoke_status") == "explicit_surface_static_proven"

    if reason_code is not None:
        capture_status = "blocked_unsafe_surface"
        task_ref = None
    elif not explicit_surface_ready:
        capture_status = "typed_unavailable"
        reason_code = "explicit_gateway_surface_not_proven"
        task_ref = None
    elif not task_ref:
        capture_status = "typed_unavailable"
        reason_code = "bg_task_ref_not_found_in_gateway_output"
    else:
        capture_status = "captured"

    captured = capture_status == "captured"
    source_refs = [str(ref) for ref in evidence_refs]
    source_refs.extend(str(ref) for ref in invocation_smoke.get("source_refs") or [])

    payload = {
        "schema_version": "hermes_background_task_capture.v1",
        "capture_id": uuid.uuid4().hex,
        "provider_id": str(provider_descriptor.get("provider_id")),
        "provider_profile": str(provider_descriptor.get("provider_profile")),
        "provider_session_id": str(provider_descriptor.get("provider_session_id")),
        "capture_status": capture_status,
        "reason_code": reason_code,
        "command": "/background",
        "invocation_surface": "provider_owned_command_gateway" if captured else "none",
        "capture_mode": "gateway_output_capture" if captured else "not_executed",
        "captured_from": "provider_owned_command_gateway_output" if captured else "none",
        "captured_task_ref": task_ref if captured else None,
        "task_ref_status": "captured" if captured else "unavailable",
        "output_sha256": _sha256_text(output_text) if output_text else None,
        "raw_output_copied": False,
        "raw_session_copied": False,
        "state_db_result_harvested": False,
        "live_provider_invoked": bool(live_provider_invoked),
        "lease_completion_claimed": False,
        "source_refs": source_refs[:24],
        "next_action": P4_H3_ACTION if captured else P4_H2_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_background_task_capture(payload)
    return payload
