from __future__ import annotations

from runtime.common.provider_wake_markers import (
    PROVIDER_REJUDGMENT_WAKE_SENTINEL,
    is_provider_rejudgment_wakeup_text,
)
from runtime.delivery.postman_cpr_wakeup import _build_provider_cpr_wakeup_prompt
from runtime.delivery.postman_cpr_wakeup import _ready_prompt_after_busy_marker
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

    assert "OpenYggdrasil 결과 도착 알림입니다" in prompt
    assert "Provider-bound 상태가 갱신" in prompt
    assert "원 질문과 현재 답을 다시 비교하세요" in prompt
    assert "support_facts_preview" not in prompt
    assert "provider_rejudgment action" not in prompt
    assert "로컬 파일 탐색" in prompt
    assert "./scripts/ygg cpr만 실행" in prompt
    assert "pipe/python/find/read는 쓰지 마세요" in prompt
    assert "파일 경로, 노드 ID, receipt ID" in prompt
    assert "답변 근거가 아니며 판단도 아닙니다" in prompt
    assert PROVIDER_REJUDGMENT_WAKE_SENTINEL not in prompt
    assert not any(marker in prompt for marker in MOJIBAKE_MARKERS)
    assert is_provider_rejudgment_wakeup_text(prompt)


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
