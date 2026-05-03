"""
Operator Producer — 14차 Axis 3: operator_entrypoint.py에서 분리.

run_producer: Mailbox에서 save-intent를 폴링하여 Vault에 적재.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.logging import log_event

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ptc.primitives import (
    extract_decisions,
    build_spo_triples,
    build_vault_node,
    save_to_vault,
    search_vault_by_keyword,
    load_vault,
    assign_edges,
    save_edges,
    _validate_admission,
    _run_feedback_loop,
)

from runtime.operator.helpers import (
    deliver_receipt,
    _update_status,
    _update_manifest,
    _ensure_q13_dirs,
    _write_context_bundle,
)
from runtime.operator.prune import (
    _handle_prune,
    _restore_from_archive,
    _handle_skill_update,
    _read_last_curation,
    _days_since,
    _run_hygiene_check,
)

from runtime.ptc.sandbox_executor import execute_ptc_code


def run_producer(mailbox: Path, vault: Path):
    """Mailbox에서 save-intent를 폴링하여 Vault에 적재."""
    # ★ 14차 Axis 4: sandbox smoketest
    try:
        from runtime.sandbox import sandbox_run
        sandbox_run(["python3", "--version"], timeout=10)
        log_event("sandbox_check_ok")
    except Exception:
        log_event("sandbox_check_skip")

    # POC Phase 0+: intents.jsonl 우선, legacy messages.jsonl 폴백
    messages_file = mailbox / "intents.jsonl"
    if not messages_file.exists():
        messages_file = mailbox / "messages.jsonl"
    receipts_file = mailbox / "receipts.jsonl"

    if not messages_file.exists():
        log_event("producer_no_messages")
        return

    # Load completed
    completed = set()
    if receipts_file.exists():
        for line in receipts_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line).get("in_reply_to"))

    # Process pending
    for line in messages_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg.get("intent") not in ("save", "prune", "curate", "skill_update", "restore", "sandbox-exec") or msg["mail_id"] in completed:
            continue

        # ★ 14차 Axis 4: sandbox-exec intent 처리 (PTC 코드 실행)
        if msg.get("intent") == "sandbox-exec":
            result = _handle_sandbox_exec(mailbox, vault, msg)
            with open(receipts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": result.get("status", "error"),
                    "intent": "sandbox-exec",
                    "exit_code": result.get("exit_code"),
                    "sandbox": result.get("sandbox"),
                    "stdout": (result.get("stdout", "") or "")[:2000],
                    "stderr": (result.get("stderr", "") or "")[:2000],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            continue

        # ★ Q13: prune intent 처리
        if msg.get("intent") == "prune":
            _handle_prune(mailbox, vault, msg)
            # Mark as completed
            with open(receipts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": "acknowledged",
                    "intent": "prune",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            continue

        # ★ Q13: curate intent 처리 (curate→_handle_prune)
        if msg.get("intent") == "curate":
            _handle_prune(mailbox, vault, msg)
            with open(receipts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": "acknowledged",
                    "intent": "curate",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            continue

        # ★ Q13: restore intent 처리 (restore→_restore_from_archive)
        if msg.get("intent") == "restore":
            node_id = msg.get("payload", {}).get("node_id", "")
            restored = _restore_from_archive(mailbox, vault, node_id)
            with open(receipts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": "acknowledged",
                    "intent": "restore",
                    "node_id": node_id,
                    "restored": restored,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            continue

        # ★ Q13: skill_update intent 처리 (skill_update→_handle_skill_update)
        if msg.get("intent") == "skill_update":
            _handle_skill_update(mailbox, msg)
            with open(receipts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": "acknowledged",
                    "intent": "skill_update",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            continue

        # ★ Phase 2: PTC 대체 경로 — LLM 코드가 전체 체인을 자유 조합
        if msg.get("payload", {}).get("ptc"):
            ptc_code = msg["payload"].get("ptc_code", "")
            if ptc_code.strip():
                result = execute_ptc_code(ptc_code, vault, mode="ipc", timeout=120)
                nodes_produced = _count_ptc_saves(result)
                receipt = {
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": "acknowledged",
                    "produced_count": nodes_produced,
                    "ptc_mode": True,
                    "ptc_stdout": (result.get("stdout", "") or "")[:500],
                    "ptc_stderr": (result.get("stderr", "") or "")[:500],
                    "ptc_status": result.get("status"),
                    "ptc_exit": result.get("exit_code"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                with open(receipts_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(receipt, ensure_ascii=False) + "\n")
                deliver_receipt(mailbox, msg["mail_id"], status="delivered", produced_count=nodes_produced)
            continue

        snapshot = msg["payload"]["context_snapshot"]
        candidates = extract_decisions(snapshot)
        nodes = []
        all_edges = []

        # Vault를 한 번만 로딩 (per message)
        existing_nodes = load_vault(vault)

        # ★ PTC Advisory: Amundsen 보조 — 카테고리 배치 힌트
        _ptc_placement_hint(mailbox, vault, snapshot)

        for c in candidates:
            triples = build_spo_triples([c], c["marker"])
            for spo in triples:
                node = build_vault_node(spo, metadata={"provider_id": msg.get("provider_id", "unknown")})
                # P0 Admission Gate: Vault 진입 전 최소 품질 검증
                passed, reason = _validate_admission(node)
                if not passed:
                    rejection_receipt = {
                        "receipt_id": str(uuid.uuid4())[:8],
                        "in_reply_to": msg["mail_id"],
                        "status": "rejected",
                        "reason": reason,
                        "gate": "admission_gate.v1",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    with open(receipts_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rejection_receipt, ensure_ascii=False) + "\n")
                    continue
                path = save_to_vault(vault, node)
                nodes.append(node["node_id"])

                # ★ 엣지 할당: 기존 노드와의 관계 설정 (Q05 엣지 온톨로지)
                edges = assign_edges(node, existing_nodes)
                if edges:
                    save_edges(vault, edges)
                    all_edges.extend(edges)

                # 현재 노드를 existing_nodes에 추가 (같은 메시지 내 후속 SPO 참조용)
                existing_nodes.append(node)

        # ★ Q13: context bundle 적재 (관련 Vault 기록 검색)
        context_dir, _ = _ensure_q13_dirs(mailbox)
        if nodes:
            # 첫 번째 노드의 subject로 관련 기록 검색
            first_subject = ""
            for n in existing_nodes[-len(nodes):]:
                first_subject = n.get("spo", {}).get("subject", "")
                if first_subject:
                    break
            if first_subject:
                related = search_vault_by_keyword(load_vault(vault), first_subject)
                _write_context_bundle(context_dir, related)

        receipt = {
            "receipt_id": str(uuid.uuid4())[:8],
            "in_reply_to": msg["mail_id"],
            "status": "acknowledged",
            "produced_count": len(nodes),
            "nodes": nodes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "producer_pid": os.getpid(),
        }
        with open(receipts_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt, ensure_ascii=False) + "\n")

        # ★ Reverse Push: Operator → Provider 영수증 발행
        deliver_receipt(mailbox, msg["mail_id"],
            status="delivered", produced_count=len(nodes), node_ids=nodes)

        # ★ status.json 갱신 (POC Phase 1 — Context Fade 복원용)
        _update_status(mailbox, intents_processed=len(completed) + 1)
        # ★ manifest.json 갱신 (POC Phase 1 — 세션 카탈로그)
        _update_manifest(mailbox, state="alive")

    # ★ Q13: 기생형 Gardener 트리거 (7일 주기)
    _ensure_q13_dirs(mailbox)
    last_curation = _read_last_curation(mailbox)
    if _days_since(last_curation) >= 7:
        _run_hygiene_check(mailbox, vault)

    # P1 피드백 루프: Gardener receipts -> prune/curate intent 발행
    feedback_stats = _run_feedback_loop(mailbox)
    if any(v > 0 for v in feedback_stats.values()):
        log_event("feedback_loop", stats=feedback_stats)

    log_event("producer_done", pid=os.getpid())


def _handle_sandbox_exec(mailbox: Path, vault: Path, msg: dict) -> dict:
    """intent: sandbox-exec 처리 — LLM 코드를 bubblewrap 클린룸에서 실행.

    msg["payload"]["code"]: LLM이 작성한 Python 코드
    msg["payload"]["timeout"]: (선택) 실행 제한 시간(초), 기본 120
    """
    code = msg.get("payload", {}).get("code", "")
    timeout = msg.get("payload", {}).get("timeout", 120)

    if not code.strip():
        return {"status": "error", "stderr": "empty code", "exit_code": -1, "sandbox": "none"}

    log_event("sandbox_exec_start", code_len=len(code), timeout=timeout)
    result = execute_ptc_code(code, vault, timeout=timeout)
    log_event("sandbox_exec_done",
              status=result.get("status"),
              exit_code=result.get("exit_code"),
              sandbox=result.get("sandbox", "unknown"))

    return result


def _ptc_placement_hint(mailbox: Path, vault: Path, snapshot: str) -> None:
    """PTC Advisory: Amundsen 카테고리 판단 전 suggest_placement 호출.

    실패해도 고정 체인을 중단하지 않는다. 로그만 남긴다.
    """
    subject = snapshot[:200] if snapshot else ""
    if not subject.strip():
        return
    try:
        result = execute_ptc_code(
            code=f'suggest_placement("{subject}")',
            vault=vault,
            mode="ipc",
            timeout=15,
        )
        stdout = result.get("stdout", "")
        if stdout:
            try:
                parsed = json.loads(stdout.strip().split("\n")[-1])
                hint = parsed.get("result", {})
                log_event("ptc_placement_hint",
                          suggested=hint.get("suggested_category"),
                          confidence=hint.get("category_confidence"),
                          similar=hint.get("similar_count"))
            except Exception:
                pass
    except Exception:
        pass  # PTC 실패는 고정 체인을 막지 않음


def _count_ptc_saves(result: dict) -> int:
    """PTC 실행 결과에서 save_note 호출 횟수를 추정."""
    stdout = result.get("stdout", "") or ""
    if not stdout.strip():
        return 0
    try:
        parsed = json.loads(stdout.strip().split("\n")[-1])
        res = parsed.get("result", {})
        if isinstance(res, dict):
            if "saved_count" in res:
                return res["saved_count"]
            if res.get("status") == "saved":
                return 1
            # Heuristic: final - initial node count difference
            if "final" in res and "initial" in res:
                return max(0, res["final"] - res["initial"])
        return 0
    except Exception:
        return 0
