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
UNSAFE_FEEDBACK_TOKENS = (
    "d:/",
    "c:/",
    "file://",
    "raw_transcript",
    "raw transcript",
    "transcript.txt",
    "api_key",
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


def _unsafe_feedback_tokens(payload: Mapping[str, Any]) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True, default=str).replace("\\", "/").lower()
    return [token for token in UNSAFE_FEEDBACK_TOKENS if token in serialized]


def validate_product_visible_answer_feedback_item(payload: Mapping[str, Any]) -> None:
    item = dict(payload)
    required = {
        "schema_version",
        "feedback_item_id",
        "item_status",
        "product_visible",
        "product_surface_id",
        "why_answer_id",
        "why_answer_decision",
        "answer_display_text",
        "used_memory_refs",
        "safe_evidence_pointers",
        "selection_reasons",
        "memory_ref_count",
        "safe_evidence_pointer_count",
        "selection_reason_count",
        "provenance_coverage",
        "safe_evidence_pointer_coverage",
        "selection_reason_coverage",
        "transcript_leak_count",
        "raw_provider_material_included",
        "local_filesystem_path_included",
        "created_at",
    }
    missing = sorted(required - set(item))
    if missing:
        raise ValueError(f"product visible feedback item is missing: {', '.join(missing)}")
    if item["schema_version"] != "product_visible_answer_feedback_item.v1":
        raise ValueError("invalid product visible feedback item schema_version")
    if item["item_status"] != "product_visible_feedback_ready":
        raise ValueError("feedback item must be ready for product visible routing")
    if item["product_visible"] is not True:
        raise ValueError("feedback item must be product visible")
    if not str(item["product_surface_id"]).strip():
        raise ValueError("product_surface_id is required")
    if item["why_answer_decision"] != "green_passed":
        raise ValueError("why remembered answer must be green_passed")
    if int(item["memory_ref_count"]) < 1:
        raise ValueError("feedback item requires memory refs")
    if int(item["safe_evidence_pointer_count"]) < 1:
        raise ValueError("feedback item requires safe evidence pointers")
    if int(item["selection_reason_count"]) < 1:
        raise ValueError("feedback item requires selection reasons")
    if float(item["provenance_coverage"]) < 1.0:
        raise ValueError("feedback item requires full provenance coverage")
    if float(item["safe_evidence_pointer_coverage"]) < 1.0:
        raise ValueError("feedback item requires full safe evidence coverage")
    if float(item["selection_reason_coverage"]) < 1.0:
        raise ValueError("feedback item requires full selection reason coverage")
    if int(item["transcript_leak_count"]) != 0:
        raise ValueError("feedback item must not include transcript leaks")
    if item["raw_provider_material_included"] is not False:
        raise ValueError("feedback item must not include raw provider material")
    if item["local_filesystem_path_included"] is not False:
        raise ValueError("feedback item must not include local filesystem paths")
    unsafe = _unsafe_feedback_tokens(item)
    if unsafe:
        raise ValueError(f"unsafe feedback item material included: {', '.join(unsafe)}")


def build_product_visible_answer_feedback_item(
    *,
    why_remembered_answer: Mapping[str, Any],
    product_surface_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Convert a safe why-remembered answer into a product-visible item."""

    answer = dict(why_remembered_answer)
    validate_why_remembered_answer(answer)
    product_surface = str(product_surface_id or "").strip()
    if not product_surface:
        raise ValueError("product_surface_id is required")
    item = {
        "schema_version": "product_visible_answer_feedback_item.v1",
        "feedback_item_id": uuid.uuid4().hex,
        "item_status": "product_visible_feedback_ready",
        "product_visible": True,
        "product_surface_id": product_surface,
        "why_answer_id": str(answer["answer_id"]),
        "why_answer_decision": str(answer["decision"]),
        "answer_display_text": str(answer["answer_text"]),
        "used_memory_refs": [str(ref) for ref in answer["used_memory_refs"]],
        "safe_evidence_pointers": [str(ref) for ref in answer["safe_evidence_pointers"]],
        "selection_reasons": [dict(reason) for reason in answer["selection_reasons"]],
        "memory_ref_count": len(answer["used_memory_refs"]),
        "safe_evidence_pointer_count": len(answer["safe_evidence_pointers"]),
        "selection_reason_count": len(answer["selection_reasons"]),
        "provenance_coverage": float(answer["provenance_coverage"]),
        "safe_evidence_pointer_coverage": float(answer["safe_evidence_pointer_coverage"]),
        "selection_reason_coverage": float(answer["selection_reason_coverage"]),
        "transcript_leak_count": int(answer["raw_transcript_leak_count"]),
        "raw_provider_material_included": False,
        "local_filesystem_path_included": False,
        "created_at": created_at or utc_now_iso(),
    }
    validate_product_visible_answer_feedback_item(item)
    return item
