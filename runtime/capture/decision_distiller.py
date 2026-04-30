from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable, Iterable, Mapping

from admission.decision_contracts import (
    validate_decision_candidate,
    validate_decision_candidate_batch,
    validate_decision_surface,
)
from attachments.provider_attachment import build_session_uid
from harness_common import utc_now_iso


DecisionCandidateRenderer = Callable[..., Mapping[str, Any]]
StructuredDecisionCandidateRenderer = Callable[..., Any]
STABILITY_STATES = {"provisional", "stable", "superseding"}
STRUCTURED_OUTPUT_GUARD_SCHEMA_VERSION = "decision_distiller_structured_output_guard.v1"
STRUCTURED_OUTPUT_GUARD_REASON = "provider_structured_output_guard"
FORBIDDEN_STRUCTURED_OUTPUT_KEYS = {
    "api_key",
    "apikey",
    "auth_token",
    "credential",
    "credentials",
    "local_path",
    "password",
    "profile",
    "provider_context",
    "provider_material",
    "provider_profile",
    "raw_provider_context",
    "raw_provider_material",
    "raw_session",
    "raw_text",
    "raw_transcript",
    "secret",
    "token",
    "transcript",
}
LOCAL_PATH_PATTERN = re.compile(
    r"(?:\b[A-Za-z]:[\\/][^\s\"']+|\\\\[^\s\"']+|file://|/(?:Users|home|mnt|tmp|var|etc)/[^\s\"']+)"
)
CREDENTIAL_VALUE_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|credential|password)\s*[:=]\s*['\"]?[^,\s'\"]+|sk-[A-Za-z0-9_-]{12,}"
)
PROVIDER_PROFILE_VALUE_PATTERN = re.compile(r"(?i)\b(?:provider[_ -]?profile|profile\s*[:=])")
RAW_TRANSCRIPT_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:raw[_ -]?transcript|conversation[_ -]?transcript)\s*[:=]"
)


def build_decision_distillation_prompt(*, decision_surface: Mapping[str, Any]) -> str:
    surface_json = json.dumps(dict(decision_surface), ensure_ascii=False, indent=2)
    return (
        "You are a provider-owned headless Decision Distiller for openyggdrasil.\n"
        "A foreground provider session identified a bounded decision surface.\n"
        "Extract only the durable decision candidate from that surface.\n"
        "Return ONLY one JSON object with this exact shape:\n"
        "{"
        '"decision_text":"one concise decision statement",'
        '"rationale":"short rationale",'
        '"alternatives_rejected":["rejected option"],'
        '"stability_state":"provisional",'
        '"topic_hint":"stable-topic-hint",'
        '"reason_labels":["durable_decision"],'
        '"confidence_score":0.0'
        "}\n"
        "Rules:\n"
        "- decision_text must be concrete and durable.\n"
        "- rationale must explain why the decision was made.\n"
        "- alternatives_rejected may be empty but must be present.\n"
        "- stability_state must be one of provisional, stable, superseding.\n"
        "- topic_hint should be short and durable.\n"
        "- confidence_score must be between 0.0 and 1.0.\n"
        "- If the surface is weak, still return a conservative provisional decision candidate.\n\n"
        f"Decision surface:\n{surface_json}\n"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse one standalone JSON object for legacy deterministic fixtures.

    Text parsing is not provider-owned structured-output proof; real-session
    producer quality must use the Mapping-only structured-output guard below.
    """

    stripped = text.strip()
    if not stripped:
        raise ValueError("No JSON object found in decision distillation output")
    decoder = json.JSONDecoder()
    try:
        payload, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("Decision distillation output must be exactly one standalone JSON object") from exc
    if end != len(stripped):
        raise ValueError("Decision distillation output must contain exactly one JSON object")
    if not isinstance(payload, dict):
        raise ValueError("Decision distillation output must be a JSON object")
    return payload


def _structured_output_unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": STRUCTURED_OUTPUT_GUARD_SCHEMA_VERSION,
        "status": "typed_unavailable",
        "structured_output_required": True,
        "structured_output_accepted": False,
        "provider_structured_output_proof": False,
        "raw_text_accepted_as_structured_proof": False,
        "accepted_as_pass": False,
        "candidate": None,
        "reason_codes": [STRUCTURED_OUTPUT_GUARD_REASON, reason_code],
    }


def _normalized_structured_output_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _unsafe_structured_output_reason(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = _normalized_structured_output_key(key)
            if normalized_key in FORBIDDEN_STRUCTURED_OUTPUT_KEYS:
                if "credential" in normalized_key or normalized_key in {
                    "api_key",
                    "apikey",
                    "auth_token",
                    "password",
                    "secret",
                    "token",
                }:
                    return "credential_material_not_allowed"
                if "profile" in normalized_key:
                    return "provider_profile_material_not_allowed"
                if "path" in normalized_key:
                    return "portable_local_path_material_not_allowed"
                if "transcript" in normalized_key or normalized_key in {"raw_text", "raw_session"}:
                    return "raw_transcript_material_not_allowed"
                return "provider_private_material_not_allowed"
            child_reason = _unsafe_structured_output_reason(child)
            if child_reason is not None:
                return child_reason
    elif isinstance(value, list):
        for child in value:
            child_reason = _unsafe_structured_output_reason(child)
            if child_reason is not None:
                return child_reason
    elif isinstance(value, str):
        if LOCAL_PATH_PATTERN.search(value):
            return "portable_local_path_material_not_allowed"
        if CREDENTIAL_VALUE_PATTERN.search(value):
            return "credential_material_not_allowed"
        if PROVIDER_PROFILE_VALUE_PATTERN.search(value):
            return "provider_profile_material_not_allowed"
        if RAW_TRANSCRIPT_VALUE_PATTERN.search(value):
            return "raw_transcript_material_not_allowed"
    return None


def _normalize_reason_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        label = str(item).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def _normalize_rejected_alternatives(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    alternatives: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            alternatives.append(text)
    return alternatives


def _normalize_confidence_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, score))


def _normalize_stability_state(value: Any) -> str:
    state = str(value or "provisional").strip()
    if state in STABILITY_STATES:
        return state
    return "provisional"


def _normalize_topic_hint(raw_value: Any, *, decision_surface: Mapping[str, Any]) -> str | None:
    text = str(raw_value or "").strip()
    if text:
        return text
    fallback = str(decision_surface.get("topic_hint") or "").strip()
    return fallback or None


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip().lower()).strip("-")
    return normalized or "decision"


def finalize_decision_candidate(
    *,
    decision_surface: Mapping[str, Any],
    raw_candidate: Mapping[str, Any],
    provider_id: str | None = None,
    profile: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    validate_decision_surface(decision_surface)
    if not isinstance(raw_candidate, Mapping):
        raise ValueError("raw_candidate must be a mapping")

    resolved_provider_id = str(provider_id or decision_surface["provider_id"]).strip()
    resolved_profile = str(profile or decision_surface["provider_profile"]).strip()
    resolved_session_id = str(session_id or decision_surface["provider_session_id"]).strip()
    if not resolved_provider_id or not resolved_profile or not resolved_session_id:
        raise ValueError("provider_id, profile, and session_id are required")

    session_uid = build_session_uid(
        provider_id=resolved_provider_id,
        provider_profile=resolved_profile,
        provider_session_id=resolved_session_id,
    )
    turn_start = int(decision_surface["turn_start"])
    turn_end = int(decision_surface["turn_end"])
    topic_hint = _normalize_topic_hint(raw_candidate.get("topic_hint"), decision_surface=decision_surface)
    dedup_basis = topic_hint or str(decision_surface.get("surface_summary") or "")
    dedup_key = f"{session_uid}:{turn_start}-{turn_end}:{_slugify(dedup_basis)}"
    candidate = {
        "schema_version": "decision_candidate.v1",
        "candidate_id": uuid.uuid4().hex,
        "dedup_key": dedup_key,
        "provider_id": resolved_provider_id,
        "provider_profile": resolved_profile,
        "provider_session_id": resolved_session_id,
        "session_uid": session_uid,
        "turn_start": turn_start,
        "turn_end": turn_end,
        "surface_summary": str(decision_surface["surface_summary"]).strip(),
        "trigger_reason": str(decision_surface["trigger_reason"]).strip(),
        "decision_text": str(raw_candidate.get("decision_text") or "").strip(),
        "rationale": str(raw_candidate.get("rationale") or "").strip(),
        "alternatives_rejected": _normalize_rejected_alternatives(
            raw_candidate.get("alternatives_rejected")
        ),
        "stability_state": _normalize_stability_state(raw_candidate.get("stability_state")),
        "topic_hint": topic_hint,
        "reason_labels": _normalize_reason_labels(raw_candidate.get("reason_labels")),
        "confidence_score": _normalize_confidence_score(raw_candidate.get("confidence_score")),
        "source_ref": decision_surface.get("source_ref"),
        "origin_locator": dict(decision_surface.get("origin_locator") or {}),
        "generated_at": utc_now_iso(),
    }
    validate_decision_candidate(candidate)
    return candidate


def finalize_provider_structured_decision_candidate(
    *,
    decision_surface: Mapping[str, Any],
    structured_output: Any,
    structured_output_proof: bool = False,
    provider_id: str | None = None,
    profile: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Finalize a candidate only when provider output is a proved Mapping.

    Plain provider text and any missing structured-output proof fail closed as
    typed unavailable for the producer-quality path. extract_json_object remains
    only a legacy fixture parser and does not establish this proof. Existing
    deterministic Mapping finalization remains available through
    finalize_decision_candidate.
    """

    validate_decision_surface(decision_surface)
    if not structured_output_proof:
        return _structured_output_unavailable("missing_structured_output_proof")
    if not isinstance(structured_output, Mapping):
        return _structured_output_unavailable("provider_output_not_structured_mapping")

    unsafe_reason = _unsafe_structured_output_reason(structured_output)
    if unsafe_reason is not None:
        return _structured_output_unavailable(unsafe_reason)

    return finalize_decision_candidate(
        decision_surface=decision_surface,
        raw_candidate=structured_output,
        provider_id=provider_id,
        profile=profile,
        session_id=session_id,
    )


def _deterministic_skip_reason(raw_candidate: Any) -> str | None:
    if not isinstance(raw_candidate, Mapping):
        return "raw_candidate_not_mapping"
    if not str(raw_candidate.get("decision_text") or "").strip():
        return "missing_decision_text"
    if not str(raw_candidate.get("rationale") or "").strip():
        return "missing_rationale"
    return None


def finalize_exhaustive_decision_candidates(
    *,
    decision_surface: Mapping[str, Any],
    raw_candidates: Iterable[Any],
    provider_id: str | None = None,
    profile: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Finalize every deterministic raw candidate without semantic-worth filtering."""

    validate_decision_surface(decision_surface)
    raw_candidate_list = list(raw_candidates)
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(raw_candidate_list):
        skip_reason = _deterministic_skip_reason(raw_candidate)
        if skip_reason is not None:
            skipped.append({"index": index, "reason_code": skip_reason})
            continue
        candidates.append(
            finalize_decision_candidate(
                decision_surface=decision_surface,
                raw_candidate=dict(raw_candidate),
                provider_id=provider_id,
                profile=profile,
                session_id=session_id,
            )
        )

    reason_codes = ["distiller_exhaustive_candidate_rule"]
    exhaustiveness_status = "exhaustive" if candidates else "deterministic_skip"
    if skipped:
        reason_codes.append("deterministic_raw_candidate_skip_recorded")
    if exhaustiveness_status == "deterministic_skip":
        reason_codes.append("no_valid_raw_candidates")

    batch = {
        "schema_version": "decision_candidate_batch.v1",
        "batch_id": uuid.uuid4().hex,
        "provider_id": str(decision_surface["provider_id"]),
        "provider_profile": str(decision_surface["provider_profile"]),
        "provider_session_id": str(decision_surface["provider_session_id"]),
        "session_uid": build_session_uid(
            provider_id=str(decision_surface["provider_id"]),
            provider_profile=str(decision_surface["provider_profile"]),
            provider_session_id=str(decision_surface["provider_session_id"]),
        ),
        "turn_start": int(decision_surface["turn_start"]),
        "turn_end": int(decision_surface["turn_end"]),
        "raw_candidate_count": len(raw_candidate_list),
        "candidate_count": len(candidates),
        "skip_count": len(skipped),
        "exhaustiveness_status": exhaustiveness_status,
        "distiller_authority": "candidate_extraction_only_no_semantic_worth_filter",
        "semantic_filtering_allowed": False,
        "candidates": candidates,
        "skipped_raw_candidates": skipped,
        "reason_codes": reason_codes,
        "created_at": utc_now_iso(),
    }
    validate_decision_candidate_batch(batch)
    return batch


def distill_decision_candidate(
    *,
    decision_surface: Mapping[str, Any],
    renderer: DecisionCandidateRenderer,
    provider_id: str | None = None,
    profile: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    validate_decision_surface(decision_surface)
    raw_candidate = renderer(decision_surface=decision_surface)
    return finalize_decision_candidate(
        decision_surface=decision_surface,
        raw_candidate=raw_candidate,
        provider_id=provider_id,
        profile=profile,
        session_id=session_id,
    )


def distill_provider_structured_decision_candidate(
    *,
    decision_surface: Mapping[str, Any],
    renderer: StructuredDecisionCandidateRenderer,
    provider_id: str | None = None,
    profile: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    validate_decision_surface(decision_surface)
    structured_output = renderer(decision_surface=decision_surface)
    return finalize_provider_structured_decision_candidate(
        decision_surface=decision_surface,
        structured_output=structured_output,
        structured_output_proof=True,
        provider_id=provider_id,
        profile=profile,
        session_id=session_id,
    )
