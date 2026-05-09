from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


from runtime.attachments.provider_attachment import bootstrap_skill_provider_session
from runtime.delivery.postman_heartbeat_cpr import (
    inject_postman_heartbeat_cpr_to_provider_inbox,
    read_postman_heartbeat_cpr_packets,
)


REGRESSION_SCHEMA_VERSION = "postman_heartbeat_cpr_regression.v1"
PROVIDER_ID = "hermes"
PROVIDER_PROFILE = "openyggdrasil-provider"
PROVIDER_SESSION_ID = "postman-cpr-regression-provider"


def _live_group() -> dict[str, Any]:
    return {
        "provider": {"status": "present", "session_name": "ygg-pro1"},
        "op1": {"status": "present", "session_name": "ygg-op1"},
        "op2": {"status": "present", "session_name": "ygg-op2"},
    }


def _engine_status() -> dict[str, Any]:
    return {
        "tmux": {"status": "running", "evidence_ref": "tmux-ref://openyggdrasil/regression"},
        "watcher": {"status": "healthy", "consumer": "engine_heartbeat_coordinator"},
        "mailbox": {"status": "healthy", "namespace": "regression"},
        "receipt_registry": {"status": "ready", "receipt_id": "op2-regression-receipt"},
    }


def _ring_support_bundle() -> dict[str, Any]:
    return {
        "schema_version": "ring_support_bundle.v1",
        "topic_key": "postman-cpr-regression",
        "ring_id": "ring-postman-cpr-regression",
        "community_id": "community:postman-cpr-regression",
        "source_ref": "hermes-session-json://postman-cpr-regression-session",
        "origin_locator": "hermes-session-json://postman-cpr-regression-session#message_index=0..1",
        "provider_session_id": "postman-cpr-regression-session",
        "message_index_range": {"start": 0, "end": 1},
        "anchor_hash": "b" * 64,
        "commit_watermark": "session:postman-cpr-regression-session:message_index:1",
        "lifecycle_state": "ACTIVE",
        "current_authority": "active",
        "source_paths": [
            "vault/queries/postman-cpr-regression.md",
            "vault/_meta/provenance/postman-cpr-regression.md",
            "vault/concepts/PRN-postman-cpr-regression.md",
            "vault/communities/postman-cpr-regression.md",
        ],
        "support_facts": [
            "Engine Heartbeat CPR regression preserves MF1 evidence metadata for Provider current-dialogue handoff."
        ],
        "origin_claims": [{"claim_id": "claim:PRN-postman-cpr-regression"}],
        "recent_rings": [{"ring_id": "ring-postman-cpr-regression"}],
        "community_edges": [{"community_id": "community:postman-cpr-regression"}],
        "semantic_edges": [{"type": "PROVENANCE_RING_SUPPORTS"}],
        "korean_query_expansion": {
            "schema_version": "korean_query_expansion.v1",
            "original_query": "ㅎㄱ",
            "expansion_status": "ready",
            "expansion_tokens": ["ko_cho:ㅎㄱ", "ko_qwerty:gksrmf"],
            "expansions": ["ㅎㄱ", "한글"],
            "used_as_secondary_signal": True,
            "primary_language_analyzer": "kiwipiepy_or_existing_tokenizer",
            "hard_nonclaims": {
                "not_grammar_checker": True,
                "not_kiwi_replacement": True,
                "not_semantic_quality_proof": True,
                "not_canonical_text_rewriter": True,
                "not_es_hangul_code_copied": True,
            },
        },
    }


def build_regression_op2_receipt() -> dict[str, Any]:
    return {
        "in_reply_to": "ask-postman-cpr-regression",
        "delivery_id": "postman-cpr-regression-delivery",
        "receipt_id": "op2-cpr-regression-receipt",
        "op2_query_receipt_id": "op2-cpr-regression-query-receipt",
        "bundle": {
            "contract": "support_bundle.v1",
            "support_bundle": _ring_support_bundle(),
        },
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _contains_local_path(value: Any, workspace_root: Path) -> bool:
    text = _json_text(value).replace("\\", "/")
    workspace = str(workspace_root.resolve()).replace("\\", "/")
    forbidden = (
        workspace,
        "C:/",
        "D:/",
        "file://",
        "/home/",
        "/mnt/",
        "/tmp/",
        "//wsl",
    )
    return any(fragment and fragment in text for fragment in forbidden)


def _git_status_short(cwd: Path) -> str | None:
    if not (cwd / ".git").exists():
        return None
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _run_in_workspace(workspace_root: Path, *, cleanup_requested: bool) -> dict[str, Any]:
    workspace_root.mkdir(parents=True, exist_ok=True)
    before_git_status = _git_status_short(workspace_root)
    bootstrap_skill_provider_session(
        workspace_root=workspace_root,
        provider_id=PROVIDER_ID,
        provider_profile=PROVIDER_PROFILE,
        provider_session_id=PROVIDER_SESSION_ID,
        origin_kind="provider-thread",
        origin_locator={"thread_id": PROVIDER_SESSION_ID},
    )
    delivery = inject_postman_heartbeat_cpr_to_provider_inbox(
        workspace_root=workspace_root,
        provider_id=PROVIDER_ID,
        provider_profile=PROVIDER_PROFILE,
        provider_session_id=PROVIDER_SESSION_ID,
        live_group=_live_group(),
        engine_status=_engine_status(),
        op2_receipt=build_regression_op2_receipt(),
        created_at="2026-05-07T00:00:00+00:00",
    )
    packets = read_postman_heartbeat_cpr_packets(
        workspace_root=workspace_root,
        provider_id=PROVIDER_ID,
        provider_profile=PROVIDER_PROFILE,
        provider_session_id=PROVIDER_SESSION_ID,
    )
    payload = delivery["payload"]
    metadata = payload.get("op2_support_metadata") or {}
    korean = metadata.get("korean_query_expansion") or {}
    hard_nonclaims = payload.get("hard_nonclaims") or {}
    korean_nonclaims = korean.get("hard_nonclaims") or {}
    after_git_status = _git_status_short(workspace_root)

    checks = {
        "delivery_created": delivery.get("delivery_status") == "created",
        "operator_brief_packet": (delivery.get("packet") or {}).get("packet_type") == "operator_brief",
        "readback_single_packet": len(packets) == 1,
        "readback_message_id_matches": bool(packets) and packets[0].get("message_id") == delivery.get("message_id"),
        "payload_ready": payload.get("heartbeat_cpr_status") == "ready",
        "handoff_ready": (payload.get("provider_inbox_handoff") or {}).get("handoff_status") == "ready_for_provider_current_dialogue",
        "manual_prompt_injection_not_required": (payload.get("provider_inbox_handoff") or {}).get("manual_prompt_injection_required") is False,
        "mailbox_correlation_preserved": (payload.get("mailbox_correlation") or {}).get("mail_id") == "ask-postman-cpr-regression",
        "receipt_id_preserved": (payload.get("mailbox_correlation") or {}).get("receipt_id") == "op2-cpr-regression-receipt",
        "ring_support_schema_preserved": metadata.get("support_schema_version") == "ring_support_bundle.v1",
        "source_paths_preserved": metadata.get("source_paths") == [
            "vault/queries/postman-cpr-regression.md",
            "vault/_meta/provenance/postman-cpr-regression.md",
            "vault/concepts/PRN-postman-cpr-regression.md",
            "vault/communities/postman-cpr-regression.md",
        ],
        "source_ref_preserved": metadata.get("source_ref") == "hermes-session-json://postman-cpr-regression-session",
        "ring_id_preserved": metadata.get("ring_id") == "ring-postman-cpr-regression",
        "korean_expansion_preserved": korean.get("schema_version") == "korean_query_expansion.v1"
        and "ko_cho:ㅎㄱ" in (korean.get("expansion_tokens") or [])
        and "ko_qwerty:gksrmf" in (korean.get("expansion_tokens") or []),
        "korean_nonclaims_preserved": korean_nonclaims.get("not_grammar_checker") is True
        and korean_nonclaims.get("not_kiwi_replacement") is True
        and korean_nonclaims.get("not_semantic_quality_proof") is True,
        "global_nonclaims_preserved": hard_nonclaims.get("full_ux_passed") is False
        and hard_nonclaims.get("production_ready") is False
        and hard_nonclaims.get("readme_scorecard_promotion_allowed") is False
        and hard_nonclaims.get("postman_semantic_quality_owner") is False,
        "payload_has_no_local_paths": not _contains_local_path(payload, workspace_root),
        "readback_payload_has_no_local_paths": bool(packets) and not _contains_local_path(packets[0].get("payload"), workspace_root),
        "git_status_unchanged_when_git_workspace": before_git_status is None
        or after_git_status is None
        or before_git_status == after_git_status,
    }
    return {
        "schema_version": REGRESSION_SCHEMA_VERSION,
        "status": "pass" if all(checks.values()) else "fail",
        "workspace_root": str(workspace_root),
        "cleanup_requested": cleanup_requested,
        "checks": checks,
        "observed": {
            "message_id": delivery.get("message_id"),
            "mail_id": (payload.get("mailbox_correlation") or {}).get("mail_id"),
            "delivery_id": (payload.get("mailbox_correlation") or {}).get("delivery_id"),
            "receipt_id": (payload.get("mailbox_correlation") or {}).get("receipt_id"),
            "support_schema_version": metadata.get("support_schema_version"),
            "ring_id": metadata.get("ring_id"),
            "source_ref": metadata.get("source_ref"),
            "korean_expansion_tokens": korean.get("expansion_tokens") or [],
        },
        "hard_nonclaims": {
            "full_ux_passed": False,
            "production_ready": False,
            "readme_scorecard_promotion_allowed": False,
            "postman_semantic_quality_owner": False,
            "korean_grammar_checker": False,
            "kiwi_replacement": False,
            "semantic_quality_proof": False,
        },
    }


def run_postman_heartbeat_cpr_regression(
    *,
    workspace_root: Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Run an isolated end-to-end Engine Heartbeat CPR regression check.

    The default path uses a temporary workspace, injects a Provider-bound CPR
    packet, reads it back, and removes the workspace before returning.
    """
    if workspace_root is not None:
        summary = _run_in_workspace(workspace_root.resolve(), cleanup_requested=False)
        summary["cleanup"] = {
            "mode": "caller_owned_workspace",
            "workspace_exists_after_run": workspace_root.exists(),
        }
        return summary

    temp_root = Path(tempfile.mkdtemp(prefix="openyggdrasil-postman-cpr-regression-")).resolve()
    try:
        summary = _run_in_workspace(temp_root, cleanup_requested=cleanup)
    finally:
        if cleanup:
            shutil.rmtree(temp_root, ignore_errors=True)
    summary["cleanup"] = {
        "mode": "temporary_workspace",
        "workspace_exists_after_run": temp_root.exists(),
    }
    summary["checks"]["temporary_workspace_removed"] = cleanup and not temp_root.exists()
    summary["status"] = "pass" if all(summary["checks"].values()) else "fail"
    return summary


def main() -> int:
    summary = run_postman_heartbeat_cpr_regression()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
