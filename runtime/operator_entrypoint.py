"""
Operator Entrypoint — SKILL이 호출하는 런타임 진입점.

engine.py를 터치하지 않는다. POC에서 검증된 primitive를
runtime/ptc/primitives.py에서 import하여 SKILL 어포던스 아래에서
조합한다.

Usage (Provider SKILL → subprocess):
    python -m runtime.operator_entrypoint produce --mailbox /path/to/mailbox --vault /path/to/vault
    python -m runtime.operator_entrypoint consume --mailbox /path/to/mailbox --vault /path/to/vault
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# primitives는 같은 runtime/ptc/ 패키지에서 import
sys.path.insert(0, str(Path(__file__).parent))
from ptc.primitives import (
    extract_decisions,
    build_spo_triples,
    build_vault_node,
    save_to_vault,
    search_vault_by_keyword,
    format_consumer_result,
    load_vault,
    assign_edges,
    save_edges,
    load_edges,
)


def run_producer(mailbox: Path, vault: Path):
    """Mailbox에서 save-intent를 폴링하여 Vault에 적재."""
    # POC Phase 0+: intents.jsonl 우선, legacy messages.jsonl 폴백
    messages_file = mailbox / "intents.jsonl"
    if not messages_file.exists():
        messages_file = mailbox / "messages.jsonl"
    receipts_file = mailbox / "receipts.jsonl"

    if not messages_file.exists():
        print(json.dumps({"status": "no_messages"}))
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
        if msg.get("intent") not in ("save", "prune") or msg["mail_id"] in completed:
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

        snapshot = msg["payload"]["context_snapshot"]
        candidates = extract_decisions(snapshot)
        nodes = []
        all_edges = []

        # Vault를 한 번만 로딩 (per message)
        existing_nodes = load_vault(vault)

        for c in candidates:
            triples = build_spo_triples([c], c["marker"])
            for spo in triples:
                node = build_vault_node(spo, metadata={"provider_id": msg.get("provider_id", "unknown")})
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
        _run_piggybacked_gardener(mailbox, vault)

    print(json.dumps({"status": "producer_done", "pid": os.getpid()}))


def run_consumer(mailbox: Path, vault: Path):
    """Mailbox에서 query-intent를 폴링하여 Vault 검색 결과 반환."""
    queries_file = mailbox / "queries.jsonl"
    receipts_file = mailbox / "query_receipts.jsonl"

    if not queries_file.exists():
        print(json.dumps({"status": "no_queries"}))
        return

    # Load vault index
    vault_nodes = load_vault(vault)

    completed = set()
    if receipts_file.exists():
        for line in receipts_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line).get("in_reply_to"))

    for line in queries_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg["mail_id"] in completed:
            continue

        query_text = msg["payload"]["query_text"]
        matches = search_vault_by_keyword(query_text, vault_nodes)
        bundle = format_consumer_result(query_text, matches)

        receipt = {
            "receipt_id": str(uuid.uuid4())[:8],
            "in_reply_to": msg["mail_id"],
            "status": "completed",
            "bundle": bundle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "consumer_pid": os.getpid(),
        }
        with open(receipts_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt, ensure_ascii=False) + "\n")

        # ★ Reverse Push: Operator → Provider 영수증 발행
        deliver_receipt(mailbox, msg["mail_id"],
            status="completed", result_bundle=bundle)

    print(json.dumps({"status": "consumer_done", "pid": os.getpid()}))


# ─── POC Phase 1: 상태 갱신 유틸리티 ───

def _update_status(mailbox: Path, *, intents_processed: int = 0):
    """status.json 갱신 — Context Fade 복원을 위한 최신 상태 스냅샷."""
    status_file = mailbox / "status.json"
    current = {}
    if status_file.exists():
        try:
            current = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass

    summary = current.get("session_summary", {})
    summary["intents_processed"] = intents_processed
    summary["intents_pending"] = max(0, summary.get("intents_received", 0) - intents_processed)

    current["operator_state"] = "alive"
    current["session_summary"] = summary
    current["last_updated"] = datetime.now(timezone.utc).isoformat()

    status_file.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def _update_manifest(mailbox: Path, *, state: str = "alive"):
    """manifest.json 갱신 — 활성 세션 카탈로그."""
    # session_id는 mailbox 경로에서 추출: .../active/{session_id}/
    session_id = mailbox.name if mailbox.name.startswith("hermes-") else "hermes-A"

    # manifest.json 탐색: active/{session}/ → active/ → mailbox root
    manifest_file = None
    for ancestor in [mailbox.parent, mailbox.parent.parent, mailbox.parent.parent.parent]:
        candidate = ancestor / "manifest.json"
        if candidate.exists():
            manifest_file = candidate
            break
    if manifest_file is None:
        return  # manifest가 없으면 skip

    current = {}
    try:
        current = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        pass

    sessions = current.get("active_sessions", [])
    # 기존 세션 갱신 또는 추가
    updated = False
    for s in sessions:
        if s.get("session_id") == session_id:
            s["operator_state"] = state
            s["intents_pending"] = 0
            updated = True
            break
    if not updated:
        sessions.append({
            "session_id": session_id,
            "provider_type": "hermes",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "operator_state": state,
            "intents_pending": 0,
        })

    current["active_sessions"] = sessions
    current["last_updated"] = datetime.now(timezone.utc).isoformat()
    manifest_file.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── 양방향 Mailbox 통신 (9차 로드맵 — Reverse Push 스터브) ───

def deliver_receipt(
    mailbox: Path,
    mail_id: str,
    *,
    status: str = "delivered",
    result_bundle: dict | None = None,
    produced_count: int = 0,
    node_ids: list[str] | None = None,
) -> dict:
    """
    [9차 로드맵 — 메일박스 Reverse Push 스터브]

    Q10 보고서 기반: Operator가 처리 완료된 결과를 Provider에게 역방향 통지.
    현재는 delivery_receipts.jsonl에 단순 Append.
    향후 SQLite WAL 기반 우선순위 큐(postman)와 연동 예정.

    Args:
        mailbox: 메일박스 디렉토리 경로
        mail_id: 응답 대상 메시지 ID
        status: 배달 상태 (delivered / failed / typed_unavailable)
        result_bundle: Consumer 검색 결과 번들 (consumer 모드 시)
        produced_count: Producer가 생성한 노드 수
        node_ids: 생성된 노드 ID 목록

    Returns:
        발행된 영수증 dict
    """
    mailbox.mkdir(parents=True, exist_ok=True)
    delivery_file = mailbox / "delivery_receipts.jsonl"

    receipt = {
        "receipt_id": str(uuid.uuid4())[:8],
        "in_reply_to": mail_id,
        "status": status,
        "produced_count": produced_count,
        "nodes": node_ids or [],
        "bundle": result_bundle,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operator_pid": os.getpid(),
        "_stub_q10_reverse_push": True,
        "_stub_note": "향후 postman 데몬이 이 파일을 감시하여 Provider에게 역방향 배달",
    }

    with open(delivery_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(receipt, ensure_ascii=False) + "\n")

    return receipt


# ─── Q13 증분 진화: context/ + curation/ ───

def _handle_prune(mailbox: Path, vault: Path, msg: dict) -> None:
    """intent: prune 처리 — Gardener 페르소나로 SUPERSEDED 정리."""
    topic_hint = msg.get("payload", {}).get("context_snapshot", "")
    vault_nodes = load_vault(vault)
    edges = load_edges(vault)

    # 대상 topic 관련 SUPERSEDED 노드 식별
    target_ids = set()
    for edge in edges:
        if edge.get("edge_type") == "SUPERSEDES":
            # topic_hint 키워드가 포함된 subject의 SUPERSEDED 노드 수집
            for node in vault_nodes:
                if node["node_id"] in (edge["from"], edge["to"]):
                    subject = node.get("spo", {}).get("subject", "")
                    if any(kw in subject for kw in topic_hint.split() if len(kw) > 1):
                        target_ids.add(edge["to"])  # 구버전 노드

    if not target_ids:
        _run_piggybacked_gardener(mailbox, vault)  # fallback: 전체 대상
        return

    # 대상 SUPERSEDED 노드들 → archive/로 격리
    archive_dir = mailbox.parent / "archive" / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_dir.mkdir(parents=True, exist_ok=True)
    for node in vault_nodes:
        if node["node_id"] in target_ids:
            # 노드 파일을 archive로 이동
            for md_file in vault.rglob(f"{node['node_id']}.md"):
                dest = archive_dir / md_file.name
                md_file.rename(dest)


def _ensure_q13_dirs(mailbox: Path) -> tuple[Path, Path]:
    """active/{session}/ 하위 context/ + curation/ 자동 생성."""
    context_dir = mailbox / "context"
    curation_dir = mailbox / "curation"
    context_dir.mkdir(exist_ok=True)
    curation_dir.mkdir(exist_ok=True)
    (curation_dir / "reports").mkdir(exist_ok=True)
    return context_dir, curation_dir


def _write_context_bundle(context_dir: Path, related_nodes: list[dict]) -> Path | None:
    """Vault 검색 결과를 context_bundle.md로 적재."""
    if not related_nodes:
        return None
    bundle_path = context_dir / "context_bundle.md"
    lines = ["# Context Bundle\n", f"generated: {datetime.now(timezone.utc).isoformat()}\n"]
    for i, node in enumerate(related_nodes[:5], 1):  # 최대 5건
        spo = node.get("spo", {})
        lines.append(f"## {i}. {spo.get('subject', node.get('node_id', '?'))}\n")
        lines.append(f"- node_id: {node.get('node_id', '?')}\n")
        lines.append(f"- category: {spo.get('category', '?')}\n")
        lines.append(f"- source: {spo.get('source_sentence', '?')[:120]}\n\n")
    bundle_path.write_text("".join(lines), encoding="utf-8")
    return bundle_path


def _read_last_curation(mailbox: Path) -> str | None:
    """curation/last_run.json에서 마지막 큐레이션 timestamp 반환."""
    last_run_file = mailbox / "curation" / "last_run.json"
    if not last_run_file.exists():
        return None
    try:
        data = json.loads(last_run_file.read_text(encoding="utf-8"))
        return data.get("last_run")
    except (json.JSONDecodeError, ValueError):
        return None


def _days_since(timestamp_iso: str | None) -> int:
    """주어진 timestamp로부터 경과 일수. None이면 큰 값 반환(즉시 실행)."""
    if timestamp_iso is None:
        return 999
    try:
        from datetime import datetime as dt
        then = dt.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        now = dt.now(timezone.utc)
        return (now - then).days
    except (ValueError, TypeError):
        return 999


def _run_piggybacked_gardener(mailbox: Path, vault: Path) -> None:
    """기생형 Gardener: last_run.json 갱신 + 보고서 생성."""
    curation_dir = mailbox / "curation"
    now_iso = datetime.now(timezone.utc).isoformat()

    # last_run.json 갱신
    (curation_dir / "last_run.json").write_text(
        json.dumps({"last_run": now_iso, "mode": "piggybacked"}, indent=2),
        encoding="utf-8")

    # 보고서 생성 (스터브)
    report_path = curation_dir / "reports" / f"{now_iso[:10]}_REPORT.md"
    report_path.write_text(
        f"# Gardener Report — {now_iso[:10]}\n\n"
        f"**Mode:** piggybacked (기생형)\n"
        f"**Status:** stub — 실제 가지치기 로직 미구현\n"
        f"**Vault:** {vault}\n",
        encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="openyggdrasil Operator Entrypoint")
    parser.add_argument("mode", choices=["produce", "consume"])
    parser.add_argument("--mailbox", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    args = parser.parse_args()

    if args.mode == "produce":
        run_producer(args.mailbox, args.vault)
    else:
        run_consumer(args.mailbox, args.vault)
