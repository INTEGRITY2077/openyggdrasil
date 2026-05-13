from __future__ import annotations

from runtime.polling.ygg_poll_context import *  # noqa: F401,F403
from runtime.polling.mailbox_summary import *  # noqa: F401,F403
from runtime.polling.receipt_quality import *  # noqa: F401,F403

def _run_operator_entrypoint_once(cmd: list[str], mail_id: str, attempt: int) -> tuple[subprocess.CompletedProcess, int, dict]:
    started = time.time()
    runtime_state_root = VAULT.parent / "runtime_state" / op_type
    runtime_state_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OPENYGGDRASIL_RUNTIME_STATE_ROOT"] = str(runtime_state_root)
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    elapsed_ms = int((time.time() - started) * 1000)
    receipt = _receipt_for_mail_id(mail_id)
    return result, elapsed_ms, {
        "attempt": attempt,
        "returncode": result.returncode,
        "elapsed_ms": elapsed_ms,
        "receipt_id": receipt.get("receipt_id"),
        "receipt_status": receipt.get("status"),
    }

def _run_operator_entrypoint_until_goal(cmd: list[str], mail_id: str) -> tuple[subprocess.CompletedProcess, int, dict, list[dict]]:
    max_attempts = max(1, int(os.environ.get("OY_OP_GOAL_MAX_ATTEMPTS", "2")))
    attempts = []
    total_elapsed_ms = 0
    last_result = None
    receipt = {}
    for attempt in range(1, max_attempts + 1):
        last_result, elapsed_ms, attempt_row = _run_operator_entrypoint_once(cmd, mail_id, attempt)
        total_elapsed_ms += elapsed_ms
        receipt = _receipt_for_mail_id(mail_id)
        attempt_row["receipt_id"] = receipt.get("receipt_id")
        attempt_row["receipt_status"] = receipt.get("status")
        attempts.append(attempt_row)
        if receipt:
            break
        if attempt < max_attempts:
            time.sleep(1.0)
    return last_result, total_elapsed_ms, receipt, attempts

def _retry_query_text(event: dict, attempt: int) -> str:
    mission = _mission_text(event)
    lower = mission.lower()
    if any(term in lower for term in ("hook", "hooks", "skill", "skills", "claude code")):
        hint = (
            "Claude Code Hooks Skills 기준, 이벤트 자동 실행, 모델 작업 지침, "
            "저장 직후 검사, 답변 품질 판단, Hook Skill boundary"
        )
    else:
        hint = (
            "원 질문의 고유명사와 제약을 유지하고, 같은 도메인/같은 맥락의 다른 표현, "
            "한국어/영어 변형, 최근 topic/community/source path 후보"
        )
    return (
        f"{mission} "
        f"재검색 attempt {attempt}: 같은 질문을 {hint} 기준으로 다시 찾는다."
    ).strip()

def _run_consumer_retry_once(event: dict, attempt: int) -> tuple[subprocess.CompletedProcess, int, dict, dict]:
    mail_id = str(event.get("mail_id") or "unknown")
    retry_mail_id = f"{mail_id}-retry{attempt}"
    retry_root = MAILBOX / "_live_goal_retries" / mail_id / f"attempt-{attempt}"
    retry_root.mkdir(parents=True, exist_ok=True)
    retry_query = {
        "mail_id": retry_mail_id,
        "intent": "query",
        "payload": {
            "query_text": _retry_query_text(event, attempt),
        },
        "created_at": time.time(),
        "retry_for": mail_id,
    }
    with open(retry_root / "queries.jsonl", "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(retry_query, ensure_ascii=False) + "\n")
    started = time.time()
    env = os.environ.copy()
    env["OPENYGGDRASIL_RUNTIME_STATE_ROOT"] = str(VAULT.parent / "runtime_state" / op_type / "retry")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runtime.operator_entrypoint",
            "consume",
            "--mailbox",
            str(retry_root),
            "--vault",
            str(VAULT),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    elapsed_ms = int((time.time() - started) * 1000)
    retry_receipt = {}
    for row in reversed(_read_jsonl(retry_root / "query_receipts.jsonl")):
        if row.get("in_reply_to") == retry_mail_id or row.get("mail_id") == retry_mail_id:
            retry_receipt = row
            break
    summary = _receipt_public_summary_for_event(event, retry_receipt)
    row = {
        "attempt": attempt,
        "retry_mail_id": retry_mail_id,
        "returncode": result.returncode,
        "elapsed_ms": elapsed_ms,
        "quality": summary["quality"],
        "result": summary["result"],
        "support_score": _receipt_support_score(retry_receipt),
        "receipt_status": retry_receipt.get("status"),
        "stdout_preview": (result.stdout or "").strip()[:240],
        "stderr_preview": (result.stderr or "").strip()[:240],
    }
    return result, elapsed_ms, retry_receipt, row

def _run_consumer_bounded_retries(event: dict, baseline_receipt: dict | None) -> tuple[dict, list[dict]]:
    if MODE != "consume":
        return baseline_receipt or {}, []
    max_retries = max(0, int(os.environ.get("OY_OP_GOAL_MAX_RETRIES", "2")))
    best_receipt = baseline_receipt or {}
    best_score = _receipt_support_score(best_receipt)
    retry_rows: list[dict] = []
    if _receipt_quality_for_event(event, best_receipt) in {"pass", "pass_with_limit"}:
        return best_receipt, retry_rows
    for attempt in range(1, max_retries + 1):
        _result, _elapsed_ms, retry_receipt, row = _run_consumer_retry_once(event, attempt)
        retry_rows.append(row)
        score = _receipt_support_score(retry_receipt)
        if score > best_score:
            best_score = score
            best_receipt = retry_receipt
        if _receipt_quality_for_event(event, best_receipt) in {"pass", "pass_with_limit"}:
            break
    return best_receipt, retry_rows


__all__ = [
    "_run_operator_entrypoint_once",
    "_run_operator_entrypoint_until_goal",
    "_retry_query_text",
    "_run_consumer_retry_once",
    "_run_consumer_bounded_retries",
]
