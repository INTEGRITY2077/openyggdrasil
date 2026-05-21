from __future__ import annotations

import re
import uuid
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from runtime.common.contract_validation import validate_contract_payload
from runtime.common.portable_ref import looks_like_local_path


PROVIDER_SUPPORT_CONSUMPTION_RECEIPT_SCHEMA = (
    "provider_support_consumption_receipt.v1.schema.json"
)

SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
FORBIDDEN_VISIBLE_MARKERS = (
    "OpenYggdrasil result arrived",
    "OpenYggdrasil 결과 도착",
    "Provider-bound",
    "./scripts/ygg cpr",
    "ygg cpr",
    "route-only",
    "wakeup-only",
    "receipt ID",
    "node ID",
    "work_order_id",
    "mail_id",
)


def _safe_identifier(value: object, *, fallback: str) -> str:
    text = str(value or "").strip() or fallback
    normalized = re.sub(r"[^A-Za-z0-9._:-]+", "-", text)[:128].strip("-")
    return normalized if IDENTIFIER_RE.match(normalized) else fallback


def _is_safe_ref(value: object) -> bool:
    text = str(value or "").strip()
    if not SAFE_REF_RE.match(text):
        return False
    if looks_like_local_path(text):
        return False
    lowered = text.lower()
    return not any(
        fragment in lowered
        for fragment in ("transcript", "credential", "receipt.json", ".env")
    )


def _safe_ref(value: object) -> str | None:
    text = str(value or "").strip()
    return text if _is_safe_ref(text) else None


def _support_metadata(cpr_read_result: Mapping[str, Any]) -> Mapping[str, Any]:
    support = cpr_read_result.get("mf1_support_metadata")
    return support if isinstance(support, Mapping) else {}


def _mailbox_correlation(cpr_read_result: Mapping[str, Any]) -> Mapping[str, Any]:
    correlation = cpr_read_result.get("mailbox_correlation")
    return correlation if isinstance(correlation, Mapping) else {}


def _forbidden_hits(answer_segment: object) -> list[str]:
    text = str(answer_segment or "")
    lowered = text.lower()
    hits: list[str] = []
    for marker in FORBIDDEN_VISIBLE_MARKERS:
        if marker.lower() in lowered:
            hits.append(marker)
    if looks_like_local_path(text):
        hits.append("local_path")
    return sorted(set(hits))


def _count_list(value: object) -> int:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return len(value)
    return 0


def validate_provider_support_consumption_receipt(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "provider_support_consumption_receipt.v1":
        raise ValueError("invalid provider support consumption schema_version")
    if payload.get("status") not in {"consumed", "typed_unavailable"}:
        raise ValueError("invalid provider support consumption status")
    if payload.get("production_readiness_claimed") is not False:
        raise ValueError("provider support consumption must not claim production readiness")
    if payload.get("full_ux_passed") is not False:
        raise ValueError("provider support consumption must not claim full UX pass")

    route = payload.get("route_free_surface")
    if not isinstance(route, Mapping):
        raise ValueError("route_free_surface is required")
    for key in (
        "visible_cpr_command_used",
        "visible_route_notice_present",
        "tmux_pane_write_attempted",
        "manual_prompt_injection_required",
        "provider_context_window_written",
    ):
        if route.get(key) is not False:
            raise ValueError(f"route-free surface requires {key}=false")
    if route.get("forbidden_marker_hits") not in ([], None):
        raise ValueError("route-free surface cannot contain forbidden marker hits")

    if payload.get("status") == "consumed":
        if payload.get("route_free_consumption_proven") is not True:
            raise ValueError("consumed receipt requires route_free_consumption_proven=true")
        if not payload.get("support_packet_ref") or not _is_safe_ref(payload.get("support_packet_ref")):
            raise ValueError("consumed receipt requires safe support_packet_ref")
        if not payload.get("answer_segment_ref") or not _is_safe_ref(payload.get("answer_segment_ref")):
            raise ValueError("consumed receipt requires safe answer_segment_ref")
    else:
        if payload.get("route_free_consumption_proven") is not False:
            raise ValueError("typed_unavailable receipt requires route_free_consumption_proven=false")
        if not payload.get("unavailable_condition"):
            raise ValueError("typed_unavailable receipt requires unavailable_condition")

    validate_contract_payload(payload, PROVIDER_SUPPORT_CONSUMPTION_RECEIPT_SCHEMA)


def build_provider_support_consumption_receipt(
    *,
    run_id: str,
    cpr_read_result: Mapping[str, Any],
    answer_segment: str,
    support_packet_ref: str | None,
    answer_segment_ref: str | None,
    answer_support_alignment: str = "not_evaluated",
) -> dict[str, Any]:
    """Build a route-free Provider support consumption receipt.

    This proves only that a Provider-side runtime surface consumed a typed MF1
    support packet without visible CPR/route notice markers and that a bounded
    answer segment can be associated with that consumption. It does not prove
    the model's private mental state, full UX completion, or production
    readiness.
    """

    support = _support_metadata(cpr_read_result)
    correlation = _mailbox_correlation(cpr_read_result)
    support_facts_count = int(
        support.get("support_facts_count")
        if support.get("support_facts_count") is not None
        else _count_list(support.get("support_facts"))
    )
    source_paths_count = int(
        support.get("source_paths_count")
        if support.get("source_paths_count") is not None
        else _count_list(support.get("source_paths"))
    )
    typed_unavailable_present = bool(support.get("typed_unavailable_present"))
    forbidden_hits = _forbidden_hits(answer_segment)

    reason_codes: list[str] = []
    if cpr_read_result.get("schema_version") != "ygg_provider_cpr_inbox_read.v1":
        reason_codes.append("cpr_read_schema_missing")
    if cpr_read_result.get("status") != "done":
        reason_codes.append("cpr_read_not_done")
    if cpr_read_result.get("handoff_status") != "ready_for_provider_current_dialogue":
        reason_codes.append("handoff_not_ready_for_current_dialogue")
    if cpr_read_result.get("manual_prompt_injection_required") is not False:
        reason_codes.append("manual_prompt_injection_required")
    if support.get("status") != "available":
        reason_codes.append("support_not_available")
    if support_facts_count <= 0:
        reason_codes.append("support_facts_missing")
    if source_paths_count <= 0:
        reason_codes.append("source_paths_missing")
    if typed_unavailable_present:
        reason_codes.append("typed_unavailable_present")
    if forbidden_hits:
        reason_codes.append("visible_route_or_internal_marker_present")
    if not str(answer_segment or "").strip():
        reason_codes.append("answer_segment_missing")
    safe_support_packet_ref = _safe_ref(support_packet_ref)
    if not safe_support_packet_ref:
        reason_codes.append("support_packet_ref_missing_or_unsafe")
    safe_answer_segment_ref = _safe_ref(answer_segment_ref)
    if not safe_answer_segment_ref:
        reason_codes.append("answer_segment_ref_missing_or_unsafe")
    if answer_support_alignment not in {
        "enough_with_limits",
        "insufficient",
        "mismatch",
        "not_evaluated",
    }:
        reason_codes.append("invalid_answer_support_alignment")
        answer_support_alignment = "not_evaluated"

    status = "typed_unavailable" if reason_codes else "consumed"
    if status == "consumed":
        reason_codes = [
            "route_free_provider_support_consumed",
            "mf1_safe_support_available",
            "provider_rejudgment_still_required",
        ]

    payload = {
        "schema_version": "provider_support_consumption_receipt.v1",
        "consumption_id": uuid.uuid4().hex,
        "run_id": _safe_identifier(run_id, fallback="unknown-run"),
        "status": status,
        "unavailable_condition": None if status == "consumed" else "blocked_route_free_consumption",
        "reason_codes": sorted(set(reason_codes)),
        "provider_id": _safe_identifier(cpr_read_result.get("provider_id"), fallback="unknown-provider"),
        "provider_profile": _safe_identifier(
            cpr_read_result.get("provider_profile"),
            fallback="unknown-profile",
        ),
        "provider_session_id": _safe_identifier(
            cpr_read_result.get("provider_session_id"),
            fallback="unknown-session",
        ),
        "support_packet_ref": safe_support_packet_ref,
        "answer_segment_ref": safe_answer_segment_ref,
        "support_summary": {
            "mail_id": correlation.get("mail_id"),
            "message_id": cpr_read_result.get("message_id"),
            "support_facts_count": support_facts_count,
            "source_paths_count": source_paths_count,
            "typed_unavailable_present": typed_unavailable_present,
        },
        "route_free_surface": {
            "visible_cpr_command_used": False,
            "visible_route_notice_present": False,
            "tmux_pane_write_attempted": False,
            "manual_prompt_injection_required": False,
            "provider_context_window_written": False,
            "forbidden_marker_hits": [],
        },
        "provider_rejudgment": {
            "answer_segment_present": bool(str(answer_segment or "").strip()),
            "answer_support_alignment": answer_support_alignment,
            "support_still_requires_provider_judgment": True,
        },
        "route_free_consumption_proven": status == "consumed",
        "production_readiness_claimed": False,
        "full_ux_passed": False,
        "hard_nonclaims": [
            "This receipt proves route-free typed support consumption only.",
            "This receipt does not prove the model's private mental state.",
            "This receipt does not prove full Provider/MS1/MF1 live UX.",
            "This receipt does not prove production readiness.",
        ],
        "created_at": utc_now_iso(),
    }
    validate_provider_support_consumption_receipt(payload)
    return payload


__all__ = [
    "PROVIDER_SUPPORT_CONSUMPTION_RECEIPT_SCHEMA",
    "build_provider_support_consumption_receipt",
    "validate_provider_support_consumption_receipt",
]
