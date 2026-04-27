from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from attachments.provider_attachment import bootstrap_skill_provider_session
from capture.session_structure_signal import build_session_structure_signal
from harness_common import WORKSPACE_ROOT, DEFAULT_VAULT, utc_now_iso
from runner.session_signal_runner import run_session_signal_mailbox_support


ROLE_ORDER = (
    "distiller",
    "evaluator",
    "amundsen",
    "seedkeeper",
    "gardener",
    "map_maker",
    "postman",
)


def _completed_roles(chain_result: Mapping[str, Any]) -> list[str]:
    roles: list[str] = []
    for step in chain_result.get("role_steps") or []:
        if not isinstance(step, Mapping):
            continue
        role = str(step.get("role") or "").strip()
        status = str(step.get("status") or "").strip()
        if role in ROLE_ORDER and status in {"completed", "ready"}:
            roles.append(role)
    return roles


def _mailbox_packet_safe_refs(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    mailbox_support_result: Mapping[str, Any],
) -> list[str]:
    safe_refs: list[str] = []
    for ref in mailbox_support_result.get("mailbox_packet_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        message_id = str(ref.get("message_id") or "").strip()
        packet_type = str(ref.get("packet_type") or "").strip()
        if message_id and packet_type:
            safe_refs.append(
                "mailbox-packet-ref://"
                f"{provider_id}/{provider_profile}/{provider_session_id}/{message_id}"
            )
    return safe_refs


def _delivery_status(mailbox_support_result: Mapping[str, Any]) -> str | None:
    delivery = mailbox_support_result.get("inbox_delivery")
    if isinstance(delivery, Mapping):
        status = str(delivery.get("delivery_status") or "").strip()
        return status or None
    return None


def _status(
    *,
    entrypoint_status: str,
    chain_status: str,
    mailbox_support_status: str,
) -> str:
    if (
        entrypoint_status == "runner_plan_ready"
        and chain_status == "completed"
        and mailbox_support_status == "completed"
    ):
        return "completed"
    return "stopped"


def run_phase_a_mock_pipeline(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    turn_start: int,
    turn_end: int,
    trigger_type: str,
    reason_labels: list[str] | tuple[str, ...],
    surface_reason: str,
    source_path_hint: str,
    workspace_root: Path | None = None,
    vault_root: Path | None = None,
    source_ref_exists: bool = True,
    source_ref_unavailable: bool = False,
    duplicate_signal: bool = False,
    privacy_risk_detected: bool = False,
) -> dict[str, Any]:
    """Run the Phase A safe-ref mock pipeline through the mailbox boundary.

    This is a facade over existing typed runner modules. It bootstraps only the
    local provider attachment needed for mailbox delivery, builds a signal-only
    payload, and returns a portable summary without local paths or raw provider
    text. It is not physical live proof.
    """

    active_workspace = (workspace_root or WORKSPACE_ROOT).resolve()
    active_vault = (vault_root or DEFAULT_VAULT).resolve()
    active_vault.mkdir(parents=True, exist_ok=True)

    bootstrap_skill_provider_session(
        workspace_root=active_workspace,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        origin_kind="workspace-session",
        origin_locator={
            "source_ref_kind": "safe_ref_mock",
            "source_path_hint": source_path_hint,
            "turn_range": f"turns:{int(turn_start)}-{int(turn_end)}",
        },
    )
    signal = build_session_structure_signal(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        turn_start=turn_start,
        turn_end=turn_end,
        trigger_type=trigger_type,
        reason_labels=reason_labels,
        surface_reason=surface_reason,
        source_path_hint=source_path_hint,
        priority="immediate",
    )
    pipeline = run_session_signal_mailbox_support(
        signal,
        workspace_root=active_workspace,
        vault_root=active_vault,
        source_ref_exists=source_ref_exists,
        source_ref_unavailable=source_ref_unavailable,
        duplicate_signal=duplicate_signal,
        privacy_risk_detected=privacy_risk_detected,
    )
    entrypoint_result = dict(pipeline["entrypoint_result"])
    chain_result = dict(pipeline["chain_result"])
    mailbox_support_result = dict(pipeline["mailbox_support_result"])
    entrypoint_status = str(entrypoint_result.get("status") or "unknown")
    chain_status = str(chain_result.get("status") or "unknown")
    mailbox_support_status = str(mailbox_support_result.get("status") or "unknown")
    completed_roles = _completed_roles(chain_result)
    status = _status(
        entrypoint_status=entrypoint_status,
        chain_status=chain_status,
        mailbox_support_status=mailbox_support_status,
    )
    return {
        "schema_version": "phase_a_mock_pipeline_facade_result.v1",
        "facade_result_id": uuid.uuid4().hex,
        "claim_scope": "mock_safe_ref_pipeline_not_live_proof",
        "status": status,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": str(signal["session_uid"]),
        "signal_id": str(signal["signal_id"]),
        "source_ref": f"provider_session:{source_path_hint}#turns:{int(turn_start)}-{int(turn_end)}",
        "entrypoint_status": entrypoint_status,
        "chain_status": chain_status,
        "mailbox_support_status": mailbox_support_status,
        "mailbox_delivery_status": _delivery_status(mailbox_support_result),
        "completed_roles": completed_roles,
        "completed_role_count": len(completed_roles),
        "mailbox_packet_safe_refs": _mailbox_packet_safe_refs(
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
            mailbox_support_result=mailbox_support_result,
        ),
        "raw_provider_transcript_included": False,
        "provider_auth_material_included": False,
        "provider_profile_contents_included": False,
        "local_path_included": False,
        "live_session_proven": False,
        "may_claim_live_readiness": False,
        "may_claim_target_readiness": False,
        "next_action": "phase_a_mock_pipeline_green" if status == "completed" else "inspect_stopped_stage",
        "created_at": utc_now_iso(),
    }
