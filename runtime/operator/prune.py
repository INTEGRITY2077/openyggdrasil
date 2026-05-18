"""
Operator Prune — 14차 Axis 3: operator_entrypoint.py에서 분리.

_handle_prune, _classify_prune_target, _restore_from_archive, _handle_skill_update,
_read_last_curation, _days_since, _run_hygiene_check, _run_piggybacked_gardener,
and hygiene helpers (_count_contradiction_chains, _count_stale_nodes,
_drop_curate_intent, _drop_prune_intent, _write_hygiene_report, _write_last_run).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.ptc.primitives import load_vault, load_edges


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

    # ★ 12차 P1: gardener_receipts.jsonl 기록 (Feedback Loop 입력)
    gardener_receipts = mailbox / "gardener_receipts.jsonl"
    for nid in consolidated:
        with open(gardener_receipts, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "action": "prune",
                "node_id": nid,
                "disposition": "consolidated",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
    for nid in pruned:
        with open(gardener_receipts, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "action": "prune",
                "node_id": nid,
                "disposition": "pruned",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")


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
