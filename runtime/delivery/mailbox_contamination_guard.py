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
    return status in STALE_GRAPH_STATUSES


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
        reason_codes=reason_codes + ["mailbox_safe"],
        checked_at=checked_at,
    )


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
