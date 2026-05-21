from __future__ import annotations

import pytest

from runtime.common.provider_wake_markers import (
    PROVIDER_REJUDGMENT_WAKE_SENTINEL,
    is_provider_rejudgment_wakeup_text,
)
from runtime.delivery.postman_cpr_wakeup import _build_provider_cpr_wakeup_prompt
from runtime.delivery.postman_cpr_wakeup import wake_provider_with_cpr
from runtime.delivery.postman_native_activation import verify_visible_notice_contract
from runtime.delivery.worker_result_spec import build_provider_rejudgment


def test_provider_cpr_wakeup_prompt_builder_is_retired() -> None:
    with pytest.raises(RuntimeError, match="provider_visible_wakeup_prompt_retired"):
        _build_provider_cpr_wakeup_prompt(
            {
                "mf1_support_metadata": {
                    "support_facts": ["plugin agents definition/distribution location"],
                    "provider_rejudgment": {
                        "schema_version": "provider_result_rejudgment.v1",
                        "provider_action": "use_with_limits",
                    },
                }
            }
        )


def test_provider_rejudgment_legacy_marker_is_detected_only_for_ignored_history() -> None:
    assert is_provider_rejudgment_wakeup_text(f"{PROVIDER_REJUDGMENT_WAKE_SENTINEL} legacy ignored")
    assert not is_provider_rejudgment_wakeup_text("OpenYggdrasil result notice")


def test_visible_provider_cpr_wakeup_is_disabled_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OY_ALLOW_VISIBLE_PROVIDER_WAKEUP", raising=False)
    result = wake_provider_with_cpr(
        {
            "status": "done",
            "heartbeat_cpr_status": "ready",
            "handoff_status": "ready_for_provider_current_dialogue",
            "manual_prompt_injection_required": False,
            "message_id": "msg-visible-disabled",
            "mf1_support_metadata": {
                "status": "available",
                "support_facts_count": 1,
                "source_paths_count": 1,
                "typed_unavailable_present": False,
            },
        },
        registry_dir=tmp_path,
        provider_session="missing-provider-session",
        inject_visible=True,
    )

    assert result["status"] == "queued"
    assert result["reason_code"] == "provider_visible_wakeup_retired"
    assert result["delivery_mode"] == "internal_heartbeat"
    assert result["provider_context_window_written"] is False
    assert result["tmux_injection_attempted"] is False


def test_visible_provider_cpr_wakeup_env_cannot_reenable_tmux_injection(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OY_ALLOW_VISIBLE_PROVIDER_WAKEUP", "1")
    result = wake_provider_with_cpr(
        {
            "status": "done",
            "heartbeat_cpr_status": "ready",
            "handoff_status": "ready_for_provider_current_dialogue",
            "manual_prompt_injection_required": False,
            "message_id": "msg-visible-retired",
            "mf1_support_metadata": {
                "status": "available",
                "support_facts_count": 1,
                "source_paths_count": 1,
                "typed_unavailable_present": False,
            },
        },
        registry_dir=tmp_path,
        provider_session="missing-provider-session",
        inject_visible=True,
    )

    assert result["status"] == "queued"
    assert result["reason_code"] == "provider_visible_wakeup_retired"
    assert result["delivery_mode"] == "internal_heartbeat"
    assert result["provider_context_window_written"] is False
    assert result["tmux_injection_attempted"] is False
    assert "prompt_preview" not in result


def test_postman_visible_notice_is_hidden_by_default_policy() -> None:
    result = verify_visible_notice_contract()

    assert result["status"] == "pass"
    assert "defaults to 0" in result["visible_by_default_env"]
    assert result["visible_mode_policy"] == "hidden_by_default_mailbox_notice"


def test_provider_rejudgment_clarification_question_is_not_a_route_notice() -> None:
    result = build_provider_rejudgment(
        worker_result_spec={
            "worker_role": "memory_finder",
            "provider_work_anchor": {
                "schema_version": "provider_work_anchor.v1",
                "anchor_kind": "missing_anchor",
                "anchor_text": "",
                "user_question_present": False,
                "provider_initiated_need_present": False,
            },
            "support_bundle": {},
        }
    )

    question = result["clarification_request"]["question"]
    forbidden = (
        "OpenYggdrasil result",
        "Provider-bound",
        "./scripts/ygg",
        "cpr",
        "receipt ID",
        "node ID",
    )
    assert not any(term in question for term in forbidden)
