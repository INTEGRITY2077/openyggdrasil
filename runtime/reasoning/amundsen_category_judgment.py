from __future__ import annotations

import re
import uuid
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso


SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

UNSAFE_REASON_CODES = {
    "hardcoded_decision": "hardcoded_category_decision_not_allowed",
    "raw_dialogue_included": "raw_dialogue_not_allowed",
    "raw_skill_body_included": "raw_skill_body_not_allowed",
    "portable_local_path_included": "portable_local_path_not_allowed",
    "graphify_used_as_sot": "graphify_as_sot_not_allowed",
    "historical_ring_snapshot_read_capability_claimed": (
        "historical_ring_snapshot_read_claim_not_allowed"
    ),
    "standalone_llm_spawned": "standalone_llm_spawn_not_allowed",
}

DEFAULT_SAFETY_FLAGS = {
    "hardcoded_decision": False,
    "raw_dialogue_included": False,
    "raw_skill_body_included": False,
    "portable_local_path_included": False,
    "graphify_used_as_sot": False,
    "historical_ring_snapshot_read_capability_claimed": False,
    "standalone_llm_spawned": False,
}


def _as_string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _is_safe_ref(value: str) -> bool:
    stripped = value.strip()
    if not SAFE_REF_RE.match(stripped):
        return False
    if "\\" in stripped:
        return False
    if re.match(r"^[A-Za-z]:", stripped):
        return False
    return True


def _unsafe_reason_codes(flags: Mapping[str, Any]) -> list[str]:
    reason_codes: list[str] = []
    for flag_name, reason_code in UNSAFE_REASON_CODES.items():
        if flags.get(flag_name) is True:
            reason_codes.append(reason_code)
    return reason_codes


def _candidate_basis_ref(candidate: Mapping[str, Any]) -> str | None:
    basis_ref = candidate.get("basis_ref")
    if basis_ref:
        return str(basis_ref)
    basis_refs = _as_string_list(candidate.get("basis_refs"))
    return basis_refs[0] if basis_refs else None


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[float, str]:
    score = candidate.get("confidence")
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = 0.0
    category_ref = str(candidate.get("category_ref") or candidate.get("category_id") or "")
    return (-numeric_score, category_ref)


def _select_candidate(
    *,
    category_candidates: Sequence[Mapping[str, Any]],
    basis_refs: Sequence[str],
) -> Mapping[str, Any] | None:
    basis_ref_set = set(basis_refs)
    safe_candidates = []
    for candidate in category_candidates:
        basis_ref = _candidate_basis_ref(candidate)
        category_ref = str(candidate.get("category_ref") or candidate.get("category_id") or "")
        if not basis_ref or basis_ref not in basis_ref_set:
            continue
        if not category_ref or not _is_safe_ref(category_ref):
            continue
        safe_candidates.append(candidate)
    if not safe_candidates:
        return None
    return sorted(safe_candidates, key=_candidate_sort_key)[0]


def validate_amundsen_category_judgment(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "amundsen_category_judgment.v1":
        raise ValueError("invalid amundsen category judgment schema_version")
    if payload.get("judgment_status") not in {"judged", "typed_unavailable"}:
        raise ValueError("invalid amundsen category judgment status")
    for flag_name in DEFAULT_SAFETY_FLAGS:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe amundsen category judgment flag: {flag_name}")
    if payload.get("ptc_callable") is not True:
        raise ValueError("amundsen category judgment must remain PTC-callable")
    if payload.get("judgment_status") == "judged":
        if not payload.get("selected_category_ref"):
            raise ValueError("judged amundsen category judgment requires selected_category_ref")
        if not _is_safe_ref(str(payload["selected_category_ref"])):
            raise ValueError("selected_category_ref must be a safe ref")
    basis_refs = _as_string_list(payload.get("basis_refs"))
    if any(not _is_safe_ref(ref) for ref in basis_refs):
        raise ValueError("basis_refs must be safe refs")


def build_amundsen_category_judgment(
    *,
    category_request: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a deterministic category judgment for a PTC-orchestrated runtime.

    This module does not spawn an LLM, read raw dialogue, or claim historical
    ring snapshot capability. It is a small runtime owner that PTC can call
    after routing and lease boundaries have already been approved.
    """

    request = dict(category_request)
    flags = dict(DEFAULT_SAFETY_FLAGS)
    flags.update(dict(safety_flags or {}))
    flags.update({key: bool(request.get(key)) for key in DEFAULT_SAFETY_FLAGS if key in request})

    reason_codes = _unsafe_reason_codes(flags)
    basis_refs = _as_string_list(request.get("basis_refs"))
    safe_basis_refs = [ref for ref in basis_refs if _is_safe_ref(ref)]
    unsafe_basis_refs = [ref for ref in basis_refs if not _is_safe_ref(ref)]

    selected_candidate: Mapping[str, Any] | None = None
    if not reason_codes and not unsafe_basis_refs and safe_basis_refs:
        candidates = request.get("category_candidates") or ()
        if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
            selected_candidate = _select_candidate(
                category_candidates=[
                    candidate for candidate in candidates if isinstance(candidate, Mapping)
                ],
                basis_refs=safe_basis_refs,
            )

    if reason_codes:
        judgment_status = "typed_unavailable"
        decision_branch = "blocked_unsafe_input"
    elif unsafe_basis_refs:
        judgment_status = "typed_unavailable"
        decision_branch = "unsafe_basis_refs"
        reason_codes = ["unsafe_basis_refs_not_allowed"]
    elif not safe_basis_refs:
        judgment_status = "typed_unavailable"
        decision_branch = "missing_basis_refs"
        reason_codes = ["category_decision_basis_refs_required"]
    elif selected_candidate is None:
        judgment_status = "typed_unavailable"
        decision_branch = "missing_candidate_with_basis_ref"
        reason_codes = ["candidate_category_with_matching_basis_ref_required"]
    else:
        judgment_status = "judged"
        decision_branch = str(selected_candidate.get("decision_branch") or "existing_category")
        reason_codes = [
            "amundsen_category_decision_input_refs_present",
            "amundsen_category_decision_basis_refs_present",
            f"decision_branch:{decision_branch}",
        ]

    selected_category_ref = None
    selected_category_label = None
    selected_basis_ref = None
    if selected_candidate is not None and judgment_status == "judged":
        selected_category_ref = str(
            selected_candidate.get("category_ref") or selected_candidate.get("category_id")
        )
        selected_category_label = str(
            selected_candidate.get("category_label") or selected_candidate.get("label") or ""
        )
        selected_basis_ref = _candidate_basis_ref(selected_candidate)

    payload = {
        "schema_version": "amundsen_category_judgment.v1",
        "judgment_id": uuid.uuid4().hex,
        "category_request_id": str(request.get("category_request_id") or uuid.uuid4().hex),
        "candidate_ref": str(request.get("candidate_ref") or ""),
        "judgment_status": judgment_status,
        "decision_branch": decision_branch,
        "selected_category_ref": selected_category_ref,
        "selected_category_label": selected_category_label,
        "selected_basis_ref": selected_basis_ref,
        "basis_refs": safe_basis_refs,
        "unsafe_basis_ref_count": len(unsafe_basis_refs),
        "reason_codes": reason_codes,
        "ptc_callable": True,
        "runtime_owner": "runtime/reasoning/amundsen_category_judgment.py",
        "module_authority": "amundsen_category_decision_only",
        "semantic_worth_authority": "not_amundsen",
        "placement_authority": "not_amundsen",
        "hardcoded_decision": False,
        "raw_dialogue_included": False,
        "raw_skill_body_included": False,
        "portable_local_path_included": False,
        "graphify_used_as_sot": False,
        "historical_ring_snapshot_read_capability_claimed": False,
        "standalone_llm_spawned": False,
        "created_at": utc_now_iso(),
    }
    validate_amundsen_category_judgment(payload)
    return payload
