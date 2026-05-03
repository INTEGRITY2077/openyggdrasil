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
import subprocess
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
    search_vault_bm25,
    format_consumer_result,
    load_vault,
    assign_edges,
    save_edges,
    load_edges,
    _boost_by_edges,
    _validate_admission,
    _run_feedback_loop,
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
        if msg.get("intent") not in ("save", "prune", "curate", "skill_update", "restore") or msg["mail_id"] in completed:
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
        print(json.dumps({"status": "feedback_loop", "stats": feedback_stats}))

    print(json.dumps({"status": "producer_done", "pid": os.getpid()}))


def _bm25_search_vault(vault: Path, query: str, top_k: int = 20) -> list[dict] | None:
    """rank-bm25 서브프로세스 호출 → 결과 파싱. 실패 시 None."""
    bridge_script = Path(__file__).parent / "qmd_bridge.py"
    
    try:
        result = subprocess.run(
            [sys.executable, str(bridge_script), "--vault", str(vault), "--query", query, "--top-k", str(top_k)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        if data.get("status") == "ok":
            return data.get("results", [])
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, Exception):
        return None


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
        # ★ 11차 Step C: rank-bm25 검색 우선 → 기존 BM25 폴백
        bm25_results = _bm25_search_vault(vault, query_text, top_k=20)
        if bm25_results is not None and len(bm25_results) > 0:
            # BM25 결과를 vault_nodes 형식으로 매핑
            vault_index = {n["node_id"]: n for n in vault_nodes if "node_id" in n}
            matches = []
            for r in bm25_results:
                node_id = r.get("node_id", "")
                if node_id in vault_index:
                    node = dict(vault_index[node_id])
                    node["_bm25_score"] = r.get("score", 0)
                    node["_match_score"] = r.get("score", 0)
                    matches.append(node)
        else:
            # 폴백: 기존 search_vault_bm25
            matches = search_vault_bm25(vault_nodes, query_text)
        # Stage 2: ACTIVE 필터 (frontmatter status 기준)
        matches = [m for m in matches if m.get("metadata", {}).get("status", "").upper() == "ACTIVE"]
        # Stage 3: load_edges + _boost_by_edges (SUPERSEDES target 제외)
        edges = load_edges(vault)
        matches = _boost_by_edges(matches, edges)
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
        _run_hygiene_check(mailbox, vault)  # fallback: 전체 대상
        return

    # 대상 SUPERSEDED 노드들 → 통폐합(consolidated) vs 가지치기(pruned) 분류
    consolidated, pruned = _classify_prune_target(edges, vault_nodes, target_ids)

    # timeline.md 생성
    curation_dir = mailbox / "curation"
    curation_dir.mkdir(parents=True, exist_ok=True)
    (curation_dir / "reports").mkdir(parents=True, exist_ok=True)
    timeline_path = curation_dir / "reports" / "timeline.md"
    lines = [f"# Prune Timeline — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"]
    lines.append(f"- consolidated (통폐합): {len(consolidated)} nodes\n")
    lines.append(f"- pruned (가지치기): {len(pruned)} nodes\n\n")
    if consolidated:
        lines.append("## Consolidated\n")
        for nid in consolidated:
            for node in vault_nodes:
                if node["node_id"] == nid:
                    subj = node.get("spo", {}).get("subject", nid)
                    lines.append(f"- [{nid}] {subj[:80]}\n")
    if pruned:
        lines.append("\n## Pruned\n")
        for nid in pruned:
            for node in vault_nodes:
                if node["node_id"] == nid:
                    subj = node.get("spo", {}).get("subject", nid)
                    lines.append(f"- [{nid}] {subj[:80]}\n")
    timeline_path.write_text("".join(lines), encoding="utf-8")

    # 모든 대상 노드 → archive로 이관
    archive_dir = mailbox.parent / "archive" / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_dir.mkdir(parents=True, exist_ok=True)
    for node in vault_nodes:
        if node["node_id"] in target_ids:
            for md_file in vault.rglob(f"{node['node_id']}.md"):
                dest = archive_dir / md_file.name
                md_file.rename(dest)


def _classify_prune_target(edges, vault_nodes, target_ids):
    """[Step 1] consolidated/pruned 분류"""
    consolidated, pruned = [], []
    for nid in target_ids:
        is_superseded = any(
            e.get("edge_type") == "SUPERSEDES" and e.get("to") == nid
            for e in edges)
        (consolidated if is_superseded else pruned).append(nid)
    return consolidated, pruned


def _restore_from_archive(mailbox: Path, vault: Path, node_id: str) -> bool:
    """[Step 2] archive 노드 복원"""
    archive_dir = mailbox.parent / "archive"
    restored = False
    for md_file in archive_dir.rglob(f"{node_id}.md"):
        dest = vault / "concepts" / md_file.name
        import shutil
        shutil.move(str(md_file), str(dest))
        restored = True
    return restored


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


def _run_hygiene_check(mailbox: Path, vault: Path) -> None:
    """[Step 3 Rev.3] 7일 안전망: 5항목 위생점검 (H1~H5)."""
    vault_nodes = load_vault(vault)
    edges = load_edges(vault)
    total = len(vault_nodes)

    # H4: 마지막 점검 경과일 체크 (7일 미경과 시 경량 모드)
    last_run = _read_last_curation(mailbox)
    if _days_since(last_run) < 7:
        # 경량 모드: H3(SNR)만 체크
        if total > 0:
            superseded_light = sum(1 for e in edges if e.get("edge_type") in ("SUPERSEDES", "CONTRADICTS"))
            stale_light = _count_stale_nodes(vault_nodes)
            snr = (total - stale_light) / total
            if snr <= 0.40:
                _write_hygiene_report(mailbox, superseded_light / total, 0, snr, stale_light)
        return

    if total == 0:
        _write_last_run(mailbox)
        return

    superseded = sum(1 for e in edges if e.get("edge_type") in ("SUPERSEDES", "CONTRADICTS"))
    superseded_ratio = superseded / total

    # H2: 모순 체인 수 (SUPERSEDES + CONTRADICTS 엣지 체인 길이 >= 3)
    chain_count = _count_contradiction_chains(edges, vault_nodes)

    # H5: Stale 노드 수 (3주 = 21일 이상 미참조)
    stale_count = _count_stale_nodes(vault_nodes)

    # H3: SNR (Signal-to-Noise Ratio)
    snr = (total - stale_count) / total

    # H1: SUPERSEDED 비율 >= 30% -> curate 드롭
    if superseded_ratio >= 0.3:
        _drop_curate_intent(mailbox, superseded_ratio, "H1_superseded")

    # H2: 모순 체인 >= 1개 -> prune 드롭
    if chain_count >= 1:
        _drop_prune_intent(mailbox, chain_count, "H2_contradiction_chains")

    # H3: SNR <= 0.40 -> 위생경보 (hygiene_report.json)
    if snr <= 0.40:
        _write_hygiene_report(mailbox, superseded_ratio, chain_count, snr, stale_count)

    # H5: Stale 노드 >= 10개 -> prune 드롭
    if stale_count >= 10:
        _drop_prune_intent(mailbox, stale_count, "H5_stale_nodes")

    _write_last_run(mailbox)


def _run_piggybacked_gardener(mailbox: Path, vault: Path) -> None:
    """[compat] Legacy Phase B Timer GC stub — delegates to _run_hygiene_check + writes legacy report."""
    _run_hygiene_check(mailbox, vault)
    # Generate legacy REPORT.md for backward test compatibility
    curation_dir = mailbox / "curation"
    curation_dir.mkdir(parents=True, exist_ok=True)
    (curation_dir / "reports").mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    report_path = curation_dir / "reports" / f"{now_iso[:10]}_REPORT.md"
    report_path.write_text(
        f"# Gardener Report — {now_iso[:10]}\n\n"
        f"**Mode:** hygiene_check (delegated from piggybacked)\n"
        f"**Vault:** {vault}\n",
        encoding="utf-8")


# ─── 위생점검 헬퍼 (Rev.3) ───

def _count_contradiction_chains(edges: list, vault_nodes: list) -> int:
    """H2: SUPERSEDES/CONTRADICTS 엣지로 연결된 체인 길이 >= 3인 모순 체인 수."""
    superseded_edges = [(e["from"], e["to"]) for e in edges if e.get("edge_type") in ("SUPERSEDES", "CONTRADICTS")]
    if not superseded_edges:
        return 0

    # 인접 리스트 구성 (to -> from 방향으로 역추적)
    adj: dict[str, list[str]] = {}
    for src, dst in superseded_edges:
        adj.setdefault(dst, []).append(src)

    # DFS로 각 노드에서 시작하는 체인 길이 측정
    chain_count = 0
    visited_roots = set()

    def dfs(node: str, depth: int, root: str) -> int:
        max_depth = depth
        for next_node in adj.get(node, []):
            if next_node == root:
                continue  # 순환 방지
            d = dfs(next_node, depth + 1, root)
            max_depth = max(max_depth, d)
        return max_depth

    for dst in adj:
        if dst in visited_roots:
            continue
        chain_len = dfs(dst, 1, dst)
        if chain_len >= 3:
            chain_count += 1
            visited_roots.add(dst)

    return chain_count


def _count_stale_nodes(vault_nodes: list) -> int:
    """H5: 3주(21일) 이상 미참조된 노드 수."""
    now = datetime.now(timezone.utc)
    stale = 0
    for node in vault_nodes:
        ts_str = node.get("timestamp") or node.get("spo", {}).get("timestamp", "")
        if not ts_str:
            continue
        try:
            node_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if (now - node_ts).days >= 21:
                stale += 1
        except (ValueError, TypeError):
            continue
    return stale


def _drop_curate_intent(mailbox: Path, ratio: float, trigger: str) -> None:
    """H1 초과 시 intent: curate 드롭."""
    curate_intent = {
        "mail_id": f"hygiene-{uuid.uuid4().hex[:8]}",
        "intent": "curate",
        "payload": {
            "trigger": trigger,
            "superseded_ratio": round(ratio, 2),
            "curation_type": "hygiene",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(mailbox / "intents.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(curate_intent, ensure_ascii=False) + "\n")


def _drop_prune_intent(mailbox: Path, count: int, trigger: str) -> None:
    """H2/H5 초과 시 intent: prune 드롭."""
    prune_intent = {
        "mail_id": f"hygiene-{uuid.uuid4().hex[:8]}",
        "intent": "prune",
        "payload": {
            "trigger": trigger,
            "count": count,
            "curation_type": "hygiene",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(mailbox / "intents.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(prune_intent, ensure_ascii=False) + "\n")


def _write_hygiene_report(
    mailbox: Path,
    superseded_ratio: float,
    chain_count: int,
    snr: float,
    stale_count: int,
) -> None:
    """H3: SNR 위생경보 -> hygiene_report.json 발행."""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "hygiene_alert",
        "metrics": {
            "H1_superseded_ratio": round(superseded_ratio, 4),
            "H2_contradiction_chains": chain_count,
            "H3_snr": round(snr, 4),
            "H5_stale_nodes": stale_count,
        },
        "status": "warning" if snr <= 0.40 else "ok",
    }
    curation_dir = mailbox / "curation"
    curation_dir.mkdir(parents=True, exist_ok=True)
    (curation_dir / "hygiene_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8")


def _write_last_run(mailbox: Path) -> None:
    """H4: last_run.json 갱신 (위생점검 완료 시점 기록)."""
    curation_dir = mailbox / "curation"
    curation_dir.mkdir(parents=True, exist_ok=True)
    (curation_dir / "last_run.json").write_text(
        json.dumps({
            "last_run": datetime.now(timezone.utc).isoformat(),
            "mode": "hygiene_check",
        }, indent=2),
        encoding="utf-8")


def _handle_skill_update(mailbox: Path, msg: dict) -> None:
    """[Step 5] E12H 진화적 스킬 루프 — 오퍼레이터 지침 앵커 업데이트 스터브"""
    anchor = msg.get("payload", {}).get("anchor_key", "")
    new_value = msg.get("payload", {}).get("new_value", "")
    curation_dir = mailbox / "curation"
    curation_dir.mkdir(parents=True, exist_ok=True)
    report = curation_dir / "reports" / "skill_patch_proposal.md"
    report.write_text(
        f"# Skill Patch Proposal\n\n"
        f"- anchor: {anchor}\n- new_value: {new_value}\n"
        f"- proposed_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"- status: draft (human review required)\n"
        f"- note: E12H stub — 실제 적용은 Worker 1 승인 필요\n",
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
