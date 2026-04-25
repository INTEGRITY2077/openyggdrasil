from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_mailbox_support_result,
    validate_thin_worker_chain_result,
)
from delivery.mailbox_contamination_guard import (
    MailboxGuardPolicy,
    guard_mailbox_message,
)
from delivery.packet_factory import build_cultivated_decision_packet
from delivery.support_bundle import (
    build_support_bundle_payload,
    deliver_session_support_packet,
    validate_support_bundle,
)
from harness_common import WORKSPACE_ROOT, utc_now_iso
from retrieval.origin_shortcut_roundtrip import follow_origin_shortcut


def _string_field(payload: Mapping[str, Any], key: str, fallback: str = "unknown") -> str:
    value = str(payload.get(key) or "").strip()
    return value or fallback


def _source_ref_token(source_refs: list[dict[str, Any]]) -> str | None:
    if not source_refs:
        return None
    first = source_refs[0]
    path_hint = str(first.get("path_hint") or "").strip()
    range_hint = str(first.get("range_hint") or "").strip()
    kind = str(first.get("kind") or "provider_session").strip()
    if not path_hint:
        return None
    return f"{kind}:{path_hint}#{range_hint}" if range_hint else f"{kind}:{path_hint}"


def _mailbox_packet_refs(inbox_delivery: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(inbox_delivery, Mapping):
        return []
    return [
        {
            "message_id": str(inbox_delivery["message_id"]),
            "packet_type": "support_bundle",
            "path_hint": str(inbox_delivery.get("inbox_path") or ""),
        }
    ]


def _empty_result(
    *,
    chain_result: Mapping[str, Any],
    stop_reason: str,
    mailbox_message: Mapping[str, Any] | None = None,
    mailbox_guard_result: Mapping[str, Any] | None = None,
    support_bundle: Mapping[str, Any] | None = None,
    origin_shortcut_result: Mapping[str, Any] | None = None,
    inbox_delivery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": "mailbox_support_result.v1",
        "emission_result_id": uuid.uuid4().hex,
        "chain_result_id": _string_field(chain_result, "chain_result_id", "missing-chain-result"),
        "signal_id": _string_field(chain_result, "signal_id", "invalid-signal"),
        "provider_id": _string_field(chain_result, "provider_id"),
        "provider_profile": _string_field(chain_result, "provider_profile"),
        "provider_session_id": _string_field(chain_result, "provider_session_id"),
        "session_uid": _string_field(chain_result, "session_uid"),
        "status": "stopped",
        "stop_reason": stop_reason,
        "source_refs": [dict(ref) for ref in chain_result.get("source_refs") or [] if isinstance(ref, Mapping)]
        or [{"kind": "provider_session", "path_hint": "missing-source-ref"}],
        "mailbox_packet_refs": _mailbox_packet_refs(inbox_delivery),
        "fallback_state": {
            "fallback_used": True,
            "fallback_reason": stop_reason,
            "quarantine": False,
        },
        "mailbox_message": dict(mailbox_message) if isinstance(mailbox_message, Mapping) else None,
        "mailbox_guard_result": dict(mailbox_guard_result) if isinstance(mailbox_guard_result, Mapping) else None,
        "support_bundle": dict(support_bundle) if isinstance(support_bundle, Mapping) else None,
        "origin_shortcut_result": dict(origin_shortcut_result) if isinstance(origin_shortcut_result, Mapping) else None,
        "inbox_delivery": dict(inbox_delivery) if isinstance(inbox_delivery, Mapping) else None,
        "next_action": "stop",
        "created_at": utc_now_iso(),
    }
    validate_mailbox_support_result(result)
    return result


def _completed_result(
    *,
    chain_result: Mapping[str, Any],
    mailbox_message: Mapping[str, Any],
    mailbox_guard_result: Mapping[str, Any],
    support_bundle: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any],
    inbox_delivery: Mapping[str, Any],
) -> dict[str, Any]:
    result = {
        "schema_version": "mailbox_support_result.v1",
        "emission_result_id": uuid.uuid4().hex,
        "chain_result_id": str(chain_result["chain_result_id"]),
        "signal_id": str(chain_result["signal_id"]),
        "provider_id": str(chain_result["provider_id"]),
        "provider_profile": str(chain_result["provider_profile"]),
        "provider_session_id": str(chain_result["provider_session_id"]),
        "session_uid": str(chain_result["session_uid"]),
        "status": "completed",
        "stop_reason": None,
        "source_refs": [dict(ref) for ref in chain_result.get("source_refs") or [] if isinstance(ref, Mapping)],
        "mailbox_packet_refs": _mailbox_packet_refs(inbox_delivery),
        "fallback_state": {
            "fallback_used": False,
            "fallback_reason": None,
            "quarantine": False,
        },
        "mailbox_message": dict(mailbox_message),
        "mailbox_guard_result": dict(mailbox_guard_result),
        "support_bundle": dict(support_bundle),
        "origin_shortcut_result": dict(origin_shortcut_result),
        "inbox_delivery": dict(inbox_delivery),
        "next_action": "same_session_answer_smoke",
        "created_at": utc_now_iso(),
    }
    validate_mailbox_support_result(result)
    return result


def _support_source_message(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = dict(chain_result.get("artifacts") or {})
    cultivated_decision = artifacts.get("cultivated_decision")
    if not isinstance(cultivated_decision, Mapping):
        raise ValueError("thin chain result is missing cultivated_decision artifact")
    return build_cultivated_decision_packet(
        provider_id=str(chain_result["provider_id"]),
        profile=str(chain_result["provider_profile"]),
        session_id=str(chain_result["provider_session_id"]),
        parent_question_id=str(chain_result["signal_id"]),
        cultivated_decision=dict(cultivated_decision),
        producer="openyggdrasil-thin-worker-chain",
    )


def emit_mailbox_support_result(
    *,
    chain_result: Mapping[str, Any],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Run R3: turn a completed thin chain result into a guarded support packet."""

    try:
        validate_thin_worker_chain_result(chain_result)
    except Exception as exc:
        return _empty_result(
            chain_result=chain_result,
            stop_reason=f"chain_result_invalid:{exc.__class__.__name__}",
        )

    if chain_result.get("status") != "completed":
        return _empty_result(
            chain_result=chain_result,
            stop_reason=str(chain_result.get("stop_reason") or "thin_chain_not_completed"),
        )

    active_workspace = (workspace_root or WORKSPACE_ROOT).resolve()
    try:
        message = _support_source_message(chain_result)
        guard_result = guard_mailbox_message(
            message,
            policy=MailboxGuardPolicy(
                expected_provider_id=str(chain_result["provider_id"]),
                expected_profile=str(chain_result["provider_profile"]),
                expected_session_id=str(chain_result["provider_session_id"]),
                allowed_message_types=("cultivated_decision",),
            ),
        )
        if guard_result["verdict"] != "accept":
            return _empty_result(
                chain_result=chain_result,
                stop_reason=f"mailbox_guard_{guard_result['verdict']}",
                mailbox_message=message,
                mailbox_guard_result=guard_result,
            )

        support_bundle = build_support_bundle_payload(message, workspace_root=active_workspace)
        source_refs = [dict(ref) for ref in chain_result.get("source_refs") or [] if isinstance(ref, Mapping)]
        support_bundle["source_ref"] = support_bundle.get("source_ref") or _source_ref_token(source_refs)
        validate_support_bundle(support_bundle)

        origin_result = follow_origin_shortcut(support_bundle, workspace_root=active_workspace)
        inbox_delivery = deliver_session_support_packet(message, workspace_root=active_workspace)
        if not inbox_delivery:
            return _empty_result(
                chain_result=chain_result,
                stop_reason="session_inbox_unavailable",
                mailbox_message=message,
                mailbox_guard_result=guard_result,
                support_bundle=support_bundle,
                origin_shortcut_result=origin_result,
            )
        return _completed_result(
            chain_result=chain_result,
            mailbox_message=message,
            mailbox_guard_result=guard_result,
            support_bundle=support_bundle,
            origin_shortcut_result=origin_result,
            inbox_delivery=inbox_delivery,
        )
    except Exception as exc:
        return _empty_result(
            chain_result=chain_result,
            stop_reason=f"mailbox_support_emission_failed:{exc.__class__.__name__}",
        )
