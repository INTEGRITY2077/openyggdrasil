from __future__ import annotations

from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from runtime.capture.wiki_capture_signal import build_wiki_capture_signal, require_safe_ref
from runtime.placement.wiki_write_guard import build_wiki_write_guard


PASS_VERDICT = "PASS_P0_E12D_WIKI_SAFETY_CANDIDATE_FOR_WORKER4"
UNAVAILABLE_VERDICT = "TYPED_UNAVAILABLE_P0_E12D_WIKI_SAFETY_GAP_NAMED"


def _hard_nonclaims() -> dict[str, bool]:
    return {
        "semantic_extraction_solved_claimed": False,
        "wiki_production_safety_complete_claimed": False,
        "graphify_canonical_authority_claimed": False,
        "readiness_claimed": False,
        "product_completion_claimed": False,
    }


def _safe_ref_list(values: Sequence[str] | None) -> tuple[list[str], list[str]]:
    safe: list[str] = []
    rejected: list[str] = []
    for value in values or []:
        try:
            safe.append(require_safe_ref(str(value), field="provenance_ref"))
        except ValueError:
            rejected.append("unsafe_provenance_ref")
    return safe, rejected


def evaluate_wiki_prewrite_quality(
    *,
    candidate_markdown: str,
    quality_score: float,
    provenance_refs: Sequence[str] | None,
) -> dict[str, Any]:
    text = str(candidate_markdown or "")
    safe_provenance_refs, rejected_refs = _safe_ref_list(provenance_refs)
    reason_codes: list[str] = []
    if quality_score < 0.8:
        reason_codes.append("quality_score_below_floor")
    if not safe_provenance_refs:
        reason_codes.append("missing_provenance_ref")
    reason_codes.extend(rejected_refs)
    if "# " not in text:
        reason_codes.append("missing_markdown_title")
    if "source" not in text.lower() and "sources" not in text.lower():
        reason_codes.append("missing_source_pointer")
    return {
        "schema_version": "wiki_prewrite_quality_gate.v1",
        "quality_score": float(quality_score),
        "quality_floor": 0.8,
        "quality_gate_passed": not reason_codes,
        "safe_provenance_refs": safe_provenance_refs,
        "reason_codes": reason_codes,
    }


def _unavailable(
    *,
    reason_codes: Sequence[str],
    wiki_capture_signal: Mapping[str, Any] | None = None,
    quality_gate: Mapping[str, Any] | None = None,
    write_guard: Mapping[str, Any] | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "wiki_production_safety_runtime_gate.v1",
        "verdict": UNAVAILABLE_VERDICT,
        "reason_codes": list(reason_codes),
        "wiki_capture_signal": dict(wiki_capture_signal) if isinstance(wiki_capture_signal, Mapping) else None,
        "quality_gate": dict(quality_gate) if isinstance(quality_gate, Mapping) else None,
        "write_guard": dict(write_guard) if isinstance(write_guard, Mapping) else None,
        "language_code_path": "runtime/capture/wiki_capture_signal.py:language_code",
        "quality_gate_path": "runtime/evaluation/wiki_production_safety_gate.py:evaluate_wiki_prewrite_quality",
        "manual_edit_write_guard_path": "runtime/placement/wiki_write_guard.py:build_wiki_write_guard",
        "provenance_source_trace_path": "runtime/capture/wiki_capture_signal.py:source_trace",
        "rollback_or_atomic_write_boundary": "runtime/placement/wiki_write_guard.py:atomic_write_wiki_page",
        "worker4_verification_required": True,
        "hard_nonclaims": _hard_nonclaims(),
        "checked_at": checked_at or utc_now_iso(),
    }


def build_wiki_production_safety_runtime_gate(
    *,
    provider_id: str,
    provider_session_id: str,
    language_code: str,
    source_ref: str,
    source_turn_ref: str,
    topic_hint: str,
    target_relative_path: str,
    candidate_markdown: str,
    quality_score: float,
    provenance_refs: Sequence[str] | None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    try:
        capture_signal = build_wiki_capture_signal(
            provider_id=provider_id,
            provider_session_id=provider_session_id,
            language_code=language_code,
            source_ref=source_ref,
            source_turn_ref=source_turn_ref,
            topic_hint=topic_hint,
            emitted_at=checked_at,
        )
    except ValueError as exc:
        return _unavailable(
            reason_codes=[f"capture_signal_unavailable:{type(exc).__name__}"],
            checked_at=checked_at,
        )

    quality_gate = evaluate_wiki_prewrite_quality(
        candidate_markdown=candidate_markdown,
        quality_score=quality_score,
        provenance_refs=provenance_refs,
    )
    write_guard = build_wiki_write_guard(
        target_relative_path=target_relative_path,
        new_text=candidate_markdown,
        checked_at=checked_at,
    )
    reason_codes = [
        *list(quality_gate.get("reason_codes") or []),
        *list(write_guard.get("reason_codes") or []),
    ]
    if quality_gate.get("quality_gate_passed") is not True or write_guard.get("write_allowed") is not True:
        return _unavailable(
            reason_codes=reason_codes or ["wiki_safety_gate_failed"],
            wiki_capture_signal=capture_signal,
            quality_gate=quality_gate,
            write_guard=write_guard,
            checked_at=checked_at,
        )

    return {
        "schema_version": "wiki_production_safety_runtime_gate.v1",
        "verdict": PASS_VERDICT,
        "reason_codes": ["wiki_safety_candidate_gate_passed"],
        "wiki_capture_signal": capture_signal,
        "quality_gate": quality_gate,
        "write_guard": write_guard,
        "language_code_path": "runtime/capture/wiki_capture_signal.py:language_code",
        "quality_gate_path": "runtime/evaluation/wiki_production_safety_gate.py:evaluate_wiki_prewrite_quality",
        "manual_edit_write_guard_path": "runtime/placement/wiki_write_guard.py:build_wiki_write_guard",
        "provenance_source_trace_path": "runtime/capture/wiki_capture_signal.py:source_trace",
        "rollback_or_atomic_write_boundary": "runtime/placement/wiki_write_guard.py:atomic_write_wiki_page",
        "worker4_verification_required": True,
        "hard_nonclaims": _hard_nonclaims(),
        "checked_at": checked_at or utc_now_iso(),
    }


__all__ = [
    "build_wiki_production_safety_runtime_gate",
    "evaluate_wiki_prewrite_quality",
]
