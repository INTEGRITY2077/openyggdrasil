from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from delivery.mailbox_schema import validate_message
from harness_common import utc_now_iso


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
GUARD_RESULT_SCHEMA_PATH = CONTRACTS_ROOT / "mailbox_guard_result.v1.schema.json"

RAW_PAYLOAD_KEYS = {
    "conversation_excerpt",
    "raw_session",
    "raw_text",
    "raw_transcript",
    "transcript",
}

STALE_GRAPH_STATUSES = {"expired", "stale"}
CATEGORY_INDEX_HINT_TYPES = {
    "graph_hint",
    "map_topography",
    "community_topography",
}
CANONICAL_WRITE_STATUS_ALLOWED_FOR_HINTS = {"", "not_written"}


@dataclass(frozen=True)
class MailboxGuardPolicy:
    expected_provider_id: str | None = None
    expected_profile: str | None = None
    expected_session_id: str | None = None
    expected_topic: str | None = None
    allowed_message_types: tuple[str, ...] = ()
    max_age_seconds: int | None = None
    require_new_status: bool = True
    require_delivery_match: bool = True


@lru_cache(maxsize=1)
def load_mailbox_guard_result_schema() -> dict[str, Any]:
    return json.loads(GUARD_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_mailbox_guard_result(result: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(result), schema=load_mailbox_guard_result_schema())


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now_datetime(now: datetime | str | None) -> datetime:
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    parsed = _parse_datetime(now)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc).replace(microsecond=0)


def _contains_raw_payload_key(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in RAW_PAYLOAD_KEYS)


def _message_scope(message: Mapping[str, Any]) -> Mapping[str, Any]:
    scope = message.get("scope")
    return scope if isinstance(scope, Mapping) else {}


def _message_payload(message: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = message.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _delivery_payload(message: Mapping[str, Any]) -> Mapping[str, Any]:
    delivery = message.get("delivery")
    return delivery if isinstance(delivery, Mapping) else {}


def _add_mismatch(
    reason_codes: list[str],
    *,
    actual: Any,
    expected: str | None,
    reason_code: str,
) -> None:
    if expected is not None and str(actual or "") != expected:
        reason_codes.append(reason_code)


def _ttl_expired(message: Mapping[str, Any], *, checked_at: datetime) -> bool:
    ttl_seconds = message.get("ttl_seconds")
    created_at = _parse_datetime(message.get("created_at"))
    if not isinstance(ttl_seconds, int) or created_at is None:
        return False
    return checked_at > created_at + timedelta(seconds=ttl_seconds)


def _too_old(
    message: Mapping[str, Any],
    *,
    checked_at: datetime,
    max_age_seconds: int | None,
) -> bool:
    if max_age_seconds is None:
        return False
    created_at = _parse_datetime(message.get("created_at"))
    if created_at is None:
        return False
    return checked_at > created_at + timedelta(seconds=max_age_seconds)


def _graph_freshness_stale(payload: Mapping[str, Any]) -> bool:
    graph_freshness = payload.get("graph_freshness")
    if not isinstance(graph_freshness, Mapping):
        return False
    status = str(graph_freshness.get("status") or "").strip().lower()
    if graph_freshness.get("graph_query_used") is False:
        return False
    return status in STALE_GRAPH_STATUSES


def _is_category_index_hint(message: Mapping[str, Any]) -> bool:
    return str(message.get("message_type") or "") in CATEGORY_INDEX_HINT_TYPES


def _category_index_unauthorized_codes(message: Mapping[str, Any]) -> list[str]:
    if not _is_category_index_hint(message):
        return []
    payload = _message_payload(message)
    reason_codes: list[str] = []
    if message.get("kind") != "packet":
        reason_codes.append("category_index_wrong_kind")
    if payload.get("vault_mutation_allowed") is True:
        reason_codes.append("category_index_canonical_write_unauthorized")
    canonical_write_status = str(payload.get("canonical_write_status") or "").strip()
    if canonical_write_status not in CANONICAL_WRITE_STATUS_ALLOWED_FOR_HINTS:
        reason_codes.append("category_index_canonical_write_unauthorized")
    canonical_authority = str(payload.get("canonical_authority") or "").strip()
    if canonical_authority and canonical_authority != "not_this_contract":
        reason_codes.append("category_index_canonical_authority_unauthorized")
    if payload.get("ambiguous_memory_canonicalized") is True:
        reason_codes.append("category_index_ambiguous_memory_canonicalized")
    return reason_codes


def _category_index_hint_reason_codes(message: Mapping[str, Any]) -> list[str]:
    if not _is_category_index_hint(message):
        return []
    return [
        "category_index_hint_only",
        "promotion_request_required",
        "gate_review_required_before_canonical_write",
        "canonical_write_not_authorized",
    ]


def _delivery_mismatches_scope(message: Mapping[str, Any]) -> list[str]:
    scope = _message_scope(message)
    delivery = _delivery_payload(message)
    if not delivery:
        return []

    mismatches: list[str] = []
    profile_target = delivery.get("profile_target")
    session_target = delivery.get("session_target")
    if profile_target and profile_target != scope.get("profile"):
        mismatches.append("delivery_profile_mismatch")
    if session_target and session_target != scope.get("session_id"):
        mismatches.append("delivery_session_mismatch")
    if scope.get("session_id") and delivery.get("mode") == "push_ready" and not session_target:
        mismatches.append("delivery_session_target_missing")
    return mismatches


def _result(
    *,
    message: Mapping[str, Any],
    verdict: str,
    reason_codes: Sequence[str],
    checked_at: str,
) -> dict[str, Any]:
    action = {
        "accept": "admit",
        "quarantine": "quarantine",
        "reject": "drop",
    }[verdict]
    scope = _message_scope(message)
    result = {
        "schema_version": "mailbox_guard_result.v1",
        "message_id": message.get("message_id"),
        "message_type": message.get("message_type"),
        "verdict": verdict,
        "action": action,
        "reason_codes": list(reason_codes),
        "checked_at": checked_at,
        "scope": {
            "provider_id": scope.get("provider_id"),
            "profile": scope.get("profile"),
            "session_id": scope.get("session_id"),
            "topic": scope.get("topic"),
        },
    }
    validate_mailbox_guard_result(result)
    return result


def guard_mailbox_message(
    message: Mapping[str, Any],
    *,
    policy: MailboxGuardPolicy | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    active_policy = policy or MailboxGuardPolicy()
    checked_at_dt = _now_datetime(now)
    checked_at = checked_at_dt.replace(microsecond=0).isoformat()

    try:
        validate_message(dict(message))
    except Exception:
        return _result(
            message=message,
            verdict="reject",
            reason_codes=["schema_invalid"],
            checked_at=checked_at,
        )

    scope = _message_scope(message)
    payload = _message_payload(message)
    reason_codes = ["schema_valid"]
    reject_codes: list[str] = []
    quarantine_codes: list[str] = []

    if _contains_raw_payload_key(payload):
        reject_codes.append("payload_contains_raw_session")

    reject_codes.extend(_category_index_unauthorized_codes(message))

    if active_policy.allowed_message_types and str(message.get("message_type") or "") not in active_policy.allowed_message_types:
        quarantine_codes.append("message_type_not_allowed")

    if active_policy.require_new_status and message.get("status") != "new":
        quarantine_codes.append("status_not_new")

    _add_mismatch(
        quarantine_codes,
        actual=scope.get("provider_id"),
        expected=active_policy.expected_provider_id,
        reason_code="scope_provider_mismatch",
    )
    _add_mismatch(
        quarantine_codes,
        actual=scope.get("profile"),
        expected=active_policy.expected_profile,
        reason_code="scope_profile_mismatch",
    )
    _add_mismatch(
        quarantine_codes,
        actual=scope.get("session_id"),
        expected=active_policy.expected_session_id,
        reason_code="scope_session_mismatch",
    )
    _add_mismatch(
        quarantine_codes,
        actual=scope.get("topic"),
        expected=active_policy.expected_topic,
        reason_code="scope_topic_mismatch",
    )

    if active_policy.require_delivery_match:
        quarantine_codes.extend(_delivery_mismatches_scope(message))

    if _ttl_expired(message, checked_at=checked_at_dt):
        quarantine_codes.append("ttl_expired")
    if _too_old(message, checked_at=checked_at_dt, max_age_seconds=active_policy.max_age_seconds):
        quarantine_codes.append("created_at_too_old")
    if _graph_freshness_stale(payload):
        quarantine_codes.append("graph_freshness_stale")

    if reject_codes:
        return _result(
            message=message,
            verdict="reject",
            reason_codes=reject_codes,
            checked_at=checked_at,
        )
    if quarantine_codes:
        return _result(
            message=message,
            verdict="quarantine",
            reason_codes=reason_codes + quarantine_codes,
            checked_at=checked_at,
        )
    return _result(
        message=message,
        verdict="accept",
        reason_codes=reason_codes + ["mailbox_safe"] + _category_index_hint_reason_codes(message),
        checked_at=checked_at,
    )


def measure_decoy_support_bundle_ux_metrics(
    *,
    decoy_guard_results: Sequence[Mapping[str, Any]],
    irrelevant_memory_citation_count: int = 0,
) -> dict[str, Any]:
    """Measure UX-FS-08 decoy support bundle false accepts."""

    decoy_count = len(decoy_guard_results)
    false_accepts: list[str] = []
    rejected_with_reason = 0
    rejected_or_quarantined = 0
    for result in decoy_guard_results:
        validate_mailbox_guard_result(result)
        verdict = str(result.get("verdict") or "")
        message_id = str(result.get("message_id") or "")
        reason_codes = result.get("reason_codes")
        if verdict == "accept":
            false_accepts.append(message_id)
            continue
        rejected_or_quarantined += 1
        if isinstance(reason_codes, list) and any(str(code).strip() for code in reason_codes):
            rejected_with_reason += 1

    if rejected_or_quarantined:
        rejection_reason_coverage: float | str = rejected_with_reason / rejected_or_quarantined
    else:
        rejection_reason_coverage = "not_applicable" if decoy_count == 0 else 0.0

    decoy_false_accept_count = len(false_accepts)
    decision = (
        "green_passed"
        if (
            decoy_false_accept_count == 0
            and int(irrelevant_memory_citation_count) == 0
            and (
                rejection_reason_coverage == 1.0
                or rejection_reason_coverage == "not_applicable"
            )
        )
        else "red_captured"
    )
    return {
        "surface_id": "UX-FS-08",
        "decoy_candidate_count": decoy_count,
        "decoy_false_accept_count": decoy_false_accept_count,
        "irrelevant_memory_citation_count": int(irrelevant_memory_citation_count),
        "decoy_rejection_reason_coverage": rejection_reason_coverage,
        "accepted_decoy_message_ids": false_accepts,
        "decision": decision,
    }


def ensure_mailbox_message_accepted(
    message: Mapping[str, Any],
    *,
    policy: MailboxGuardPolicy | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    result = guard_mailbox_message(message, policy=policy, now=now)
    if result["verdict"] != "accept":
        raise ValueError(
            "Mailbox guard rejected message "
            f"{message.get('message_id') or '<unknown>'}: {', '.join(result['reason_codes'])}"
        )
    return result
