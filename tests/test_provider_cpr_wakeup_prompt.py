from __future__ import annotations

from runtime.common.provider_wake_markers import (
    PROVIDER_REJUDGMENT_WAKE_SENTINEL,
    is_provider_rejudgment_wakeup_text,
)
from runtime.delivery.postman_cpr_wakeup import _build_provider_cpr_wakeup_prompt
from runtime.delivery.worker_result_spec import build_provider_rejudgment


MOJIBAKE_MARKERS = (
    "蹂닿컯",
    "?꾩갑",
    "留덉",
    "洹쇨굅",
    "?뚯씪",
    "媛쒖닔",
)


def test_provider_cpr_wakeup_prompt_is_readable_korean_and_marker_detectable() -> None:
    prompt = _build_provider_cpr_wakeup_prompt({})

    assert "OpenYggdrasil 보강 결과가 도착했습니다" in prompt
    assert "마지막 사용자 질문" in prompt
    assert "파일 경로" in prompt
    assert "내부 식별자" in prompt
    assert "receipt ID" not in prompt
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
