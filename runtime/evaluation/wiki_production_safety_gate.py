from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any, Mapping, Sequence

from capture.wiki_capture_signal import (
    build_wiki_capture_signal,
    require_safe_ref,
    validate_wiki_capture_signal,
)
from harness_common import utc_now_iso
from placement.wiki_write_guard import build_wiki_write_guard


QUALITY_SCORE_FLOOR = 0.75
MIN_MEANINGFUL_MARKDOWN_CHARS = 80
FORBIDDEN_TEXT_PATTERN = re.compile(
    r"(?i)(raw transcript|api[_-]?key|access[_-]?token|credential|password|secret|"
    r"\b[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|mnt|tmp|var|etc)/)"
)


def _safe_digest(*parts: str) -> str:
    body = "\n".join(parts)
    return sha256(body.encode("utf-8")).hexdigest()[:16]


def _typed_unavailable(reason_codes: Sequence[str], *, checked_at: str) -> dict[str, Any]:
    return {
        "schema_version": "wiki_prewrite_quality_gate.v1",
        "status": "typed_unavailable",
        "quality_gate_passed": False,
        "score": None,
        "score_floor": QUALITY_SCORE_FLOOR,
        "quality_gate_ref": None,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "checked_at": checked_at,
    }


def evaluate_wiki_prewrite_quality(
    *,
    wiki_capture_signal: Mapping[str, Any],
    candidate_markdown: str,
    quality_score: float,
    provenance_refs: Sequence[str],
    checked_at: str | None = None,
) -> dict[str, Any]:
    checked = checked_at or utc_now_iso()
    try:
        validate_wiki_capture_signal(wiki_capture_signal)
    except Exception:
        return _typed_unavailable(["invalid_wiki_capture_signal"], checked_at=checked)

    text = str(candidate_markdown or "").strip()
    reason_codes: list[str] = []
    if len(text) < MIN_MEANINGFUL_MARKDOWN_CHARS:
        reason_codes.append("candidate_markdown_too_short")
    if FORBIDDEN_TEXT_PATTERN.search(text):
        reason_codes.append("unsafe_material_in_candidate_markdown")

    try:
        score = float(quality_score)
    except Exception:
        score = 0.0
        reason_codes.append("quality_score_not_numeric")
    if score < QUALITY_SCORE_FLOOR:
        reason_codes.append("quality_score_below_floor")

    safe_provenance_refs: list[str] = []
    for ref in provenance_refs:
        try:
            safe_provenance_refs.append(require_safe_ref(str(ref), field="provenance_ref"))
        except Exception:
            reason_codes.append("unsafe_or_missing_provenance_ref")
            break
    if not safe_provenance_refs:
        reason_codes.append("missing_provenance_ref")

    if reason_codes:
        return _typed_unavailable(reason_codes, checked_at=checked)

    source_trace = dict(wiki_capture_signal["source_trace"])
    gate_ref = (
        "wiki-quality-gate-ref://openyggdrasil/e12d/"
        + _safe_digest(str(source_trace["source_ref"]), str(source_trace["source_turn_ref"]), text)
    )
    return {
        "schema_version": "wiki_prewrite_quality_gate.v1",
        "status": "quality_gate_passed",
        "quality_gate_passed": True,
        "score": score,
        "score_floor": QUALITY_SCORE_FLOOR,
        "quality_gate_ref": gate_ref,
        "source_trace": {
            "source_ref": source_trace["source_ref"],
            "source_turn_ref": source_trace["source_turn_ref"],
            "provenance_refs": safe_provenance_refs,
        },
        "raw_transcript_included": False,
        "semantic_extraction_solved_claimed": False,
        "reason_codes": ["prewrite_quality_gate_passed"],
        "checked_at": checked,
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
    provenance_refs: Sequence[str],
    existing_text: str | None = None,
    expected_existing_hash: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    checked = checked_at or utc_now_iso()
    reason_codes: list[str] = []
    try:
        capture_signal = build_wiki_capture_signal(
            provider_id=provider_id,
            provider_session_id=provider_session_id,
            language_code=language_code,
            source_ref=source_ref,
            source_turn_ref=source_turn_ref,
            topic_hint=topic_hint,
            emitted_at=checked,
        )
    except Exception as exc:
        capture_signal = None
        reason_codes.append(f"capture_signal_unavailable:{exc}")

    if capture_signal is None:
        quality_gate = _typed_unavailable(["capture_signal_unavailable"], checked_at=checked)
    else:
        quality_gate = evaluate_wiki_prewrite_quality(
            wiki_capture_signal=capture_signal,
            candidate_markdown=candidate_markdown,
            quality_score=quality_score,
            provenance_refs=provenance_refs,
            checked_at=checked,
        )

    try:
        write_guard = build_wiki_write_guard(
            target_relative_path=target_relative_path,
            new_text=candidate_markdown,
            existing_text=existing_text,
            expected_existing_hash=expected_existing_hash,
            checked_at=checked,
        )
    except Exception as exc:
        write_guard = {
            "schema_version": "wiki_write_guard.v1",
            "status": "typed_unavailable",
            "write_allowed": False,
            "reason_codes": [f"write_guard_unavailable:{exc}"],
            "checked_at": checked,
        }

    reason_codes.extend(str(item) for item in quality_gate.get("reason_codes", []))
    reason_codes.extend(str(item) for item in write_guard.get("reason_codes", []))
    quality_ok = quality_gate.get("quality_gate_passed") is True
    write_ok = write_guard.get("write_allowed") is True
    verdict = (
        "PASS_P0_E12D_WIKI_SAFETY_CANDIDATE_FOR_WORKER4"
        if quality_ok and write_ok
        else "TYPED_UNAVAILABLE_P0_E12D_WIKI_SAFETY_GAP_NAMED"
    )
    result = {
        "schema_version": "p0_e12d_wiki_production_safety_runtime_gate.v1",
        "verdict": verdict,
        "language_code_path": "runtime/capture/wiki_capture_signal.py:language_code",
        "quality_gate_path": "runtime/evaluation/wiki_production_safety_gate.py:evaluate_wiki_prewrite_quality",
        "manual_edit_write_guard_path": "runtime/placement/wiki_write_guard.py:build_wiki_write_guard",
        "provenance_source_trace_path": "runtime/evaluation/wiki_production_safety_gate.py:source_trace",
        "rollback_or_atomic_write_boundary": "runtime/placement/wiki_write_guard.py:atomic_write_wiki_page",
        "wiki_capture_signal": capture_signal,
        "quality_gate": quality_gate,
        "write_guard": write_guard,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "hard_nonclaims": {
            "semantic_extraction_solved_claimed": False,
            "wiki_production_safety_complete_claimed": False,
            "graphify_canonical_authority_claimed": False,
            "readiness_claimed": False,
            "product_completion_claimed": False,
        },
        "worker4_verification_required": True,
        "checked_at": checked,
    }
    _assert_no_local_path_or_raw_material(result)
    return result


def _assert_no_local_path_or_raw_material(payload: Mapping[str, Any]) -> None:
    serialized = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True).replace("\\", "/")
    if FORBIDDEN_TEXT_PATTERN.search(serialized):
        raise ValueError("wiki safety gate result contains unsafe material")
