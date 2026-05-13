#!/usr/bin/env python3
"""Optional MS/MF delivery debug lens for producer/consumer mailboxes."""
from __future__ import annotations

from runtime.polling.ygg_poll_context import *  # noqa: F401,F403
from runtime.polling.mailbox_summary import *  # noqa: F401,F403
from runtime.polling.live_delivery_policy import *  # noqa: F401,F403

_workflow(
    now="메일박스 연속 감시 시작",
    watching=f"mailbox={MAILBOX}; vault={VAULT}; interval={POLL_INTERVAL}s",
    creating="미처리 intent/query 처리 결과 receipt",
    created="optional MS/MF debug lens started",
    evidence=f"{MAILBOX / intent_name}; {MAILBOX / receipt_name}",
    next_action="메일 도착 시 operator_entrypoint 실행 후 행동 카드만 출력",
    status="running",
)

while True:
    live_delivery_mode = os.environ.get("OY_LIVE_DELIVERY") == "1"
    if MODE == "produce":
        ptc_intents = _check_ptc_intents(MAILBOX)
        for ptc in ptc_intents:
            _route_ptc_to_hermes(MAILBOX, ptc)
    if live_delivery_mode:
        live_events = _check_live_events()
        for event in live_events:
            if os.environ.get("OY_OP_VISIBLE_LIVE_DELIVERY") == "1":
                _route_live_event_to_hermes(event)
            else:
                _run_live_event_quietly(event)
        time.sleep(POLL_INTERVAL)
        continue

    before_counts = _count_pending()
    before = f"{intent_name}={before_counts[0]}, {receipt_name}={before_counts[1]}, pending≈{before_counts[2]}"
    result = subprocess.run(
        [sys.executable, "-m", "runtime.operator_entrypoint", MODE,
         "--mailbox", str(MAILBOX), "--vault", str(VAULT)],
        capture_output=True, text=True, timeout=300,
    )
    after_counts = _count_pending()
    after = f"{intent_name}={after_counts[0]}, {receipt_name}={after_counts[1]}, pending≈{after_counts[2]}"

    if result.returncode != 0:
        stderr_preview = (result.stderr or "").strip().replace("\n", " | ")[:240]
        _workflow(
            now="operator_entrypoint 실행 실패 확인",
            watching=f"{MAILBOX / intent_name}; 실행 전 {before}; 실행 후 {after}",
            creating="실패 상태 카드",
            created=f"returncode={result.returncode}",
            evidence=f"stderr_preview={stderr_preview or '(empty)'}",
            next_action="stderr 원문 요청 또는 코드/환경 검증 필요",
            status="blocked",
        )
    elif result.stdout.strip():
        latest_summary = _latest_receipt_summary()
        should_report = (
            before_counts[2] > 0
            or before_counts != after_counts
            or latest_summary != "최신 receipt 없음"
        )
        if should_report:
            _workflow(
                now="operator_entrypoint 처리 결과를 행동 카드로 요약",
                watching=f"{MAILBOX / intent_name}; 실행 전 {before}; 실행 후 {after}",
                creating=f"{MAILBOX / receipt_name} 갱신",
                created=latest_summary,
                evidence=f"{MAILBOX / receipt_name}",
                next_action="pending 차집합 재확인 후 대기",
                status="done",
            )

    time.sleep(POLL_INTERVAL)
