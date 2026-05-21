from __future__ import annotations

from pathlib import Path

import pytest

from runtime.common.provider_wake_markers import (
    PROVIDER_REJUDGMENT_WAKE_SENTINEL,
    is_provider_rejudgment_wakeup_text,
)
from runtime.delivery.postman_cpr_wakeup import _build_provider_cpr_wakeup_prompt
from runtime.delivery.postman_cpr_wakeup import wake_provider_with_cpr
from runtime.delivery.postman_native_activation import _activation_prompt
from runtime.delivery.postman_native_activation import activate_native_lane
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
    assert is_provider_rejudgment_wakeup_text(
        "아까 답을 뒤에서 확인된 기준과 비교해서 필요한 밀도로 다시 봐줘. "
        "근거 이름이나 내부 번호를 나열하지는 마."
    )
    assert not is_provider_rejudgment_wakeup_text("OpenYggdrasil result notice")
    assert not is_provider_rejudgment_wakeup_text(
        "위키 근거가 있으면 뒤에서 확인해줘. 없으면 부족하다고 말해줘."
    )


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
    assert result["visible_by_default_env"] == "ignored; Postman pane notice is retired"
    assert result["visible_mode_policy"] == "postman_pane_notice_retired_worker_loop_only"
    assert result["tmux_pane_write_allowed"] is False
    assert result["worker_surface_owner"] == "MS1/MF1 worker loop after mailbox row read"


def test_worker_visible_notice_is_minimal_mail_arrival_only() -> None:
    with pytest.raises(RuntimeError, match="postman_pane_notice_retired_worker_loop_only"):
        _activation_prompt(
            label="MF1",
            role_type="consumer",
            message_type="query",
            payload={"query_text": "semantic query must not appear"},
            delivery={"mail_id": "ask-clean", "work_order_id": "work-clean"},
        )


def test_postman_native_env_cannot_reenable_worker_pane_notice(tmp_path: Path, monkeypatch) -> None:
    import runtime.delivery.postman_native_activation as activation

    monkeypatch.setenv("OY_POSTMAN_VISIBLE_CPR", "1")
    monkeypatch.setattr(activation, "_tmux_session_exists", lambda session: True)
    monkeypatch.setattr(activation, "_native_pane_target", lambda session: f"{session}:1")
    monkeypatch.setattr(
        activation,
        "_native_pane_status",
        lambda target: {"status": "idle", "reason_code": "test_idle"},
    )

    def fail_send(*args, **kwargs):  # pragma: no cover - regression guard
        raise AssertionError("Postman must not write worker pane notices")

    monkeypatch.setattr(activation, "_send_tmux_target_text", fail_send)

    result = activate_native_lane(
        op="MS1",
        label="MS1",
        role_type="producer",
        session="ygg-ms1",
        delivery={"delivery_id": "d1", "mail_id": "m1", "work_order_id": "w1"},
        message_type="memory_ticket",
        payload={"surface_reason": "must not appear"},
        registry_dir=tmp_path / "registry",
        sessions_dir=tmp_path / "sessions",
    )

    assert result["status"] == "recorded_for_worker_loop"
    assert result["reason_code"] == "postman_pane_notice_retired_worker_loop_only"
    assert result["visible_cpr"] is False
    assert result["visible_cpr_requested"] is True
    assert result["tmux_pane_write_attempted"] is False
    assert result["prompt_contract"] == "postman_does_not_write_worker_pane"


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
