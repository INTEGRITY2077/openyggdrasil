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
DEVIATION_DECISION_RECORD_SCHEMA_PATH = (
    CONTRACTS_ROOT / "deviation_decision_record.v1.schema.json"
)
UNSAFE_DEVIATION_TOKENS = (
    "d:/",
    "c:/",
    "file://",
    "raw_transcript",
    "raw transcript",
    "transcript.txt",
    "api_key",
    "apikey",
    "password",
    "secret",
    "credential",
    ".env",
)


@lru_cache(maxsize=1)
def load_deviation_decision_record_schema() -> dict[str, Any]:
    return json.loads(DEVIATION_DECISION_RECORD_SCHEMA_PATH.read_text(encoding="utf-8"))


def _clean_non_empty_strings(name: str, values: Sequence[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _unsafe_tokens(payload: Mapping[str, Any]) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True, default=str).replace("\\", "/").lower()
    return [token for token in UNSAFE_DEVIATION_TOKENS if token in serialized]


def build_deviation_correction_automation(
    *,
    correction_task_id: str,
    affected_gap_ids: Sequence[Any],
    evidence_refs: Sequence[Any],
) -> dict[str, Any]:
    task_id = str(correction_task_id or "").strip()
    if not task_id:
        raise ValueError("correction_task_id is required")
    automation = {
        "schema_version": "deviation_correction_automation.v1",
        "automation_status": "correction_required",
        "correction_task_id": task_id,
        "affected_gap_ids": _clean_non_empty_strings("affected_gap_ids", affected_gap_ids),
        "evidence_refs": _clean_non_empty_strings("evidence_refs", evidence_refs),
        "raw_provider_material_included": False,
        "local_filesystem_path_included": False,
        "live_readiness_claimed": False,
        "full_roadmap_completion_claimed": False,
    }
    unsafe = _unsafe_tokens(automation)
    if unsafe:
        raise ValueError(f"unsafe deviation correction material included: {', '.join(unsafe)}")
    return automation


def validate_deviation_decision_record(payload: Mapping[str, Any]) -> None:
    record = dict(payload)
    jsonschema.validate(
        instance=record,
        schema=load_deviation_decision_record_schema(),
    )
    automation = dict(record["correction_automation"])
    if automation["affected_gap_ids"] != record["affected_gap_ids"]:
        raise ValueError("correction automation affected gaps must match decision record")
    if automation["evidence_refs"] != record["evidence_refs"]:
        raise ValueError("correction automation evidence refs must match decision record")
    policy = dict(record["execution_policy"])
    if policy.get("decision_record_required") is not True:
        raise ValueError("deviation decision record is required")
    if policy.get("correction_automation_required") is not True:
        raise ValueError("deviation correction automation is required")
    for key in (
        "raw_provider_material_included",
        "local_filesystem_path_included",
        "live_readiness_claimed",
        "full_roadmap_completion_claimed",
    ):
        if policy.get(key) is not False or automation.get(key) is not False:
            raise ValueError(f"{key} must be false")
    unsafe = _unsafe_tokens(record)
    if unsafe:
        raise ValueError(f"unsafe deviation decision material included: {', '.join(unsafe)}")


def build_deviation_decision_record(
    *,
    deviation_kind: str,
    deviation_summary: str,
    affected_gap_ids: Sequence[Any],
    evidence_refs: Sequence[Any],
    correction_task_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    kind = str(deviation_kind or "").strip()
    summary = str(deviation_summary or "").strip()
    if not kind:
        raise ValueError("deviation_kind is required")
    if not summary:
        raise ValueError("deviation_summary is required")
    gap_ids = _clean_non_empty_strings("affected_gap_ids", affected_gap_ids)
    refs = _clean_non_empty_strings("evidence_refs", evidence_refs)
    record = {
        "schema_version": "deviation_decision_record.v1",
        "deviation_decision_id": uuid.uuid4().hex,
        "decision_status": "recorded_for_correction",
        "deviation_kind": kind,
        "deviation_summary": summary,
        "affected_gap_ids": gap_ids,
        "evidence_refs": refs,
        "correction_automation": build_deviation_correction_automation(
            correction_task_id=correction_task_id,
            affected_gap_ids=gap_ids,
            evidence_refs=refs,
        ),
        "execution_policy": {
            "decision_record_required": True,
            "correction_automation_required": True,
            "raw_provider_material_included": False,
            "local_filesystem_path_included": False,
            "live_readiness_claimed": False,
            "full_roadmap_completion_claimed": False,
        },
        "reason_codes": [
            "deviation_decision_recorded",
            "correction_automation_required",
            "raw_provider_material_not_copied",
            "readiness_not_claimed",
        ],
        "created_at": created_at or utc_now_iso(),
    }
    validate_deviation_decision_record(record)
    return record
