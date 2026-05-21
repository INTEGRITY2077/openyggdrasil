from __future__ import annotations

from runtime.common.provider_wake_markers import (
    PROVIDER_REJUDGMENT_WAKE_SENTINEL,
    is_provider_rejudgment_wakeup_text,
)
from runtime.delivery.postman_cpr_wakeup import _build_provider_cpr_wakeup_prompt
from runtime.delivery.postman_cpr_wakeup import _ready_prompt_after_busy_marker
from runtime.delivery.postman_cpr_wakeup import wake_provider_with_cpr
from runtime.delivery.postman_native_activation import verify_visible_notice_contract
from runtime.delivery.worker_result_spec import build_provider_rejudgment


MOJIBAKE_MARKERS = (
    "?꾧퉴",
    "蹂닿컯",
    "留덉",
    "洹쇨굅",
    "寃곌낵",
    "筌",
    "�",
)


def test_provider_cpr_wakeup_prompt_is_readable_korean_and_marker_detectable() -> None:
    prompt = _build_provider_cpr_wakeup_prompt(
        {
            "mf1_support_metadata": {
                "support_facts": ["plugin agents는 definition/distribution location이다."],
                "provider_rejudgment": {
                    "schema_version": "provider_result_rejudgment.v1",
                    "provider_action": "use_with_limits",
                },
            }
        }
    )

    assert prompt == "OpenYggdrasil 보강 후보가 도착했습니다. 현재 답을 다시 살펴볼 수 있습니다."
    assert "OpenYggdrasil 보강 후보" in prompt
    assert "support_facts_preview" not in prompt
    assert "provider_rejudgment action" not in prompt
    assert "로컬 파일 탐색" not in prompt
    assert "./scripts/ygg" not in prompt
    assert "cpr" not in prompt.lower()
    assert "pipe" not in prompt.lower()
    assert "python" not in prompt.lower()
    assert "find" not in prompt.lower()
    assert "read" not in prompt.lower()
    assert "파일 경로" not in prompt
    assert "노드 ID" not in prompt
    assert "receipt ID" not in prompt
    assert "답변 근거가 아니며 판단도 아닙니다" not in prompt
    assert "Provider-bound" not in prompt
    assert PROVIDER_REJUDGMENT_WAKE_SENTINEL not in prompt
    assert not any(marker in prompt for marker in MOJIBAKE_MARKERS)
    assert is_provider_rejudgment_wakeup_text(prompt)


def test_provider_cpr_wakeup_prompt_without_support_is_minimal() -> None:
    prompt = _build_provider_cpr_wakeup_prompt({"mf1_support_metadata": {}})

    assert prompt == "OpenYggdrasil 보강 후보가 부족합니다. 현재 답을 바꿀 근거가 없으면 그대로 두세요."
    assert is_provider_rejudgment_wakeup_text(prompt)
    forbidden = (
        "./scripts/ygg",
        "cpr",
        "Provider-bound",
        "로컬 파일",
        "pipe",
        "python",
        "find",
        "read",
        "파일 경로",
        "노드 ID",
        "receipt ID",
        "개수 목록",
    )
    assert not any(term in prompt for term in forbidden)


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
    assert result["reason_code"] == "visible_provider_wakeup_disabled"
    assert result["delivery_mode"] == "internal_heartbeat"
    assert result["provider_context_window_written"] is False
    assert result["tmux_injection_attempted"] is False


def test_postman_visible_notice_is_hidden_by_default_policy() -> None:
    result = verify_visible_notice_contract()

    assert result["status"] == "pass"
    assert "defaults to 0" in result["visible_by_default_env"]
    assert result["visible_mode_policy"] == "hidden_by_default_route_notice"


def test_provider_rejudgment_clarification_question_is_readable_korean() -> None:
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
    assert question == "어떤 이전 맥락을 기준으로 찾을지 한 단서만 더 알려주세요."
    assert not any(marker in question for marker in MOJIBAKE_MARKERS)


def test_provider_lane_monitor_ignores_stale_interrupted_marker_after_ready_prompt() -> None:
    capture_tail = """
Operation interrupted: waiting for model response
[Interrupted - processing new message]

╭─ ⚕ Hermes ─────────────────────────────────────────────────────────────────────╮
    현재 답변은 완료됐습니다.
╰────────────────────────────────────────────────────────────────────────────────╯
 ⚕ gpt-5.5 │ 67.4K/272K │ [██░░░░░░░░] 25% │ 54m │ ⏲ 8s
──────────────────────────────────────────────────────────────────────────────────
❯
"""

    assert _ready_prompt_after_busy_marker(capture_tail)
