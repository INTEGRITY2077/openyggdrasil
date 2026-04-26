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
WHY_REMEMBERED_ANSWER_SCHEMA_PATH = CONTRACTS_ROOT / "why_remembered_answer.v1.schema.json"
RAW_LEAK_MARKERS = (
    "raw_transcript",
    "raw transcript",
    "raw_session",
    "raw session",
    "provider transcript",
    "user:",
    "assistant:",
)


@lru_cache(maxsize=1)
def load_why_remembered_answer_schema() -> dict[str, Any]:
    return json.loads(WHY_REMEMBERED_ANSWER_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_why_remembered_answer(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_why_remembered_answer_schema())


def _clean_strings(values: Sequence[Any]) -> list[str]:
    return [str(value).strip() for value in values if str(value or "").strip()]


def _selection_reasons(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        memory_ref = str(value.get("memory_ref") or "").strip()
        reason = str(value.get("reason") or "").strip()
        if memory_ref and reason:
            reasons.append({"memory_ref": memory_ref, "reason": reason})
    return reasons


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _raw_transcript_leak_count(*values: Any) -> int:
    count = 0
    for value in values:
        if isinstance(value, Mapping):
            count += _raw_transcript_leak_count(*value.values())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            count += _raw_transcript_leak_count(*value)
        else:
            text = str(value or "").lower()
            if any(marker in text for marker in RAW_LEAK_MARKERS):
                count += 1
    return count


def build_why_remembered_answer(
    *,
    used_memory_refs: Sequence[Any],
    safe_evidence_pointers: Sequence[Any],
    selection_reasons: Sequence[Mapping[str, Any]],
    answer_text: str | None = None,
) -> dict[str, Any]:
    """Build a safe user-facing answer for "why did you remember that?"."""

    used_refs = _clean_strings(used_memory_refs)
    safe_pointers = _clean_strings(safe_evidence_pointers)
    reasons = _selection_reasons(selection_reasons)
    reason_refs = {reason["memory_ref"] for reason in reasons}
    used_ref_count = len(used_refs)

    safe_pointer_coverage = _ratio(min(len(safe_pointers), used_ref_count), used_ref_count)
    selection_reason_coverage = _ratio(sum(1 for ref in used_refs if ref in reason_refs), used_ref_count)
    provenance_coverage = min(safe_pointer_coverage, selection_reason_coverage)
    text = str(
        answer_text
        or "I remembered this because the cited memory matched the current request, and the safe evidence pointer is attached."
    ).strip()
    raw_leaks = _raw_transcript_leak_count(text, safe_pointers, reasons)

    failing: list[str] = []
    if provenance_coverage < 1.0:
        failing.append("provenance_coverage")
    if safe_pointer_coverage < 1.0:
        failing.append("safe_evidence_pointer_coverage")
    if selection_reason_coverage < 1.0:
        failing.append("selection_reason_coverage")
    if raw_leaks:
        failing.append("raw_transcript_leak_count")

    answer = {
        "schema_version": "why_remembered_answer.v1",
        "answer_id": uuid.uuid4().hex,
        "decision": "green_passed" if not failing else "red_captured",
        "answer_text": text,
        "used_memory_refs": used_refs,
        "safe_evidence_pointers": safe_pointers,
        "selection_reasons": reasons,
        "provenance_coverage": provenance_coverage,
        "safe_evidence_pointer_coverage": safe_pointer_coverage,
        "selection_reason_coverage": selection_reason_coverage,
        "selection_reason_present": selection_reason_coverage == 1.0,
        "raw_transcript_leak_count": raw_leaks,
        "failing_metrics": failing,
        "created_at": utc_now_iso(),
    }
    validate_why_remembered_answer(answer)
    return answer
