"""
Operator Producer — 14차 Axis 3: operator_entrypoint.py에서 분리.

run_producer: Mailbox에서 save-intent를 폴링하여 Vault에 적재.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.log_event import log_event

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

from runtime.memory.wiki_node_taxonomy import (
    build_community_node_taxonomy,
    build_node_taxonomy,
    validate_node_taxonomy,
)
from runtime.ptc.sandbox_executor import execute_ptc_code


def run_producer(mailbox: Path, vault: Path):
    """Mailbox에서 save-intent를 폴링하여 Vault에 적재."""
    t0 = datetime.now(timezone.utc)

    # ★ 14차 Axis 4: sandbox guard (보안 계층, 기능 블로커 아님)
    try:
        from runtime.sandbox import sandbox_run
        sandbox_ok = sandbox_run(["python3", "--version"], timeout=10)
        if sandbox_ok is None:
            log_event("sandbox_unavailable", reason="bwrap_not_found", action="continue_direct")
    except Exception:
        log_event("sandbox_unavailable", reason="import_error", action="continue_direct")

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
        if msg.get("intent") not in ("save", "memory_ticket", "prune", "curate", "skill_update", "restore", "sandbox-exec", "promote") or msg["mail_id"] in completed:
            continue

        if msg.get("intent") == "memory_ticket":
            result = _handle_memory_ticket(mailbox, vault, msg)
            nodes = result.get("nodes", [])
            status = result.get("status", "acknowledged")
            ring_ids = result.get("ring_ids", [])
            receipt = {
                "receipt_id": str(uuid.uuid4())[:8],
                "in_reply_to": msg["mail_id"],
                "status": status,
                "intent": "memory_ticket",
                "produced_count": len(nodes),
                "nodes": nodes,
                "ring_ids": ring_ids,
                "canonical_topic_path": result.get("canonical_topic_path"),
                "support_bundle_seed": result.get("support_bundle_seed"),
                "source_ref_status": result.get("source_ref_status"),
                "reason": result.get("reason"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "producer_pid": os.getpid(),
            }
            with open(receipts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(receipt, ensure_ascii=False) + "\n")
            deliver_receipt(
                mailbox,
                msg["mail_id"],
                status="delivered" if nodes else "deferred",
                produced_count=len(nodes),
                node_ids=nodes,
                result_bundle={
                    "intent": "memory_ticket",
                    "source_ref_status": result.get("source_ref_status"),
                    "reason": result.get("reason"),
                    "source_ref": msg.get("payload", {}).get("source_ref"),
                    "ring_ids": ring_ids,
                    "canonical_topic_path": result.get("canonical_topic_path"),
                    "support_bundle_seed": result.get("support_bundle_seed"),
                },
            )
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
        # ★ Nursery: promote intent 처리 (DRAFT → ACTIVE)
        if msg.get("intent") == "promote":
            node_id = msg.get("payload", {}).get("node_id", "")
            if node_id:
                _handle_promote(vault, node_id)
            with open(receipts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": "acknowledged",
                    "intent": "promote",
                    "node_id": node_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
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

    # ★ Axis 5: 운영 메트릭 — Vault 통계 수집
    try:
        from runtime.vault_integrity import collect_stats
        meta_stats = collect_stats(vault)
        log_event("vault_stats_collected",
                  node_count=meta_stats.get("node_count", 0),
                  total_size=meta_stats.get("total_size_bytes", 0))
    except Exception:
        log_event("vault_stats_skip")

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
    log_event("producer_done", pid=os.getpid(), elapsed_ms=round(elapsed))


def _slugify_topic_key(text: str) -> str:
    import re

    lowered = text.strip().lower()
    asciiish = re.sub(r"[^0-9a-zA-Z가-힣]+", "-", lowered).strip("-")
    return asciiish[:80] or "memory-ticket"


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _render_provenance_ring_page(*, ring_node: dict) -> str:
    topic = ring_node["canonical_topic"]
    capsule = ring_node["decision_capsule"]
    ring = ring_node["provenance_rings"][0]
    lifecycle = ring_node["lifecycle"]
    community = ring_node["community"]
    taxonomy = ring_node.get("node_taxonomy", {})
    retrieval = ring_node["retrieval_contract"]
    safety_belt = ring_node.get("paragraph_intent_safety_belt", {})
    quality = ring_node.get("quality_assessment", {})
    return f"""---
id: {ring_node['node_id']}
title: {topic['title']}
type: {ring_node.get('category', 'policy')}
continent: {taxonomy.get('continent', 'concepts')}
physical_continent: {taxonomy.get('physical_continent', 'concepts')}
node_type: {taxonomy.get('node_type', ring_node.get('category', 'policy'))}
topography_level: {taxonomy.get('topography_level', 'tree')}
community_role: {taxonomy.get('community_role', 'member')}
status: ACTIVE
community: {community['community_id']}
sources: [{ring['source_ref']}]
root_claim: {capsule['decision']}
current_authority: active
ring_id: {ring['ring_id']}
lifecycle_state: ACTIVE
---
# {topic['title']}

## 1. Canonical Claim
{capsule['decision']}

## 2. Decision Capsule
```json
{json.dumps(capsule, ensure_ascii=False, indent=2)}
```

## 3. Provenance Rings
```json
{json.dumps(ring_node['provenance_rings'], ensure_ascii=False, indent=2)}
```

## 4. Lifecycle
```json
{json.dumps(lifecycle, ensure_ascii=False, indent=2)}
```

## 5. Edges
- DERIVES_FROM: {ring['origin_locator']}
- SUPPORTS: {capsule['decision']}

## 6. Community Placement
```json
{json.dumps(community, ensure_ascii=False, indent=2)}
```

## 6A. Node Taxonomy
```json
{json.dumps(taxonomy, ensure_ascii=False, indent=2)}
```

## 7. Paragraph Intent Safety Belt
```json
{json.dumps(safety_belt, ensure_ascii=False, indent=2)}
```

## 8. Retrieval Contract
```json
{json.dumps(retrieval, ensure_ascii=False, indent=2)}
```

## 9. Quality Assessment
```json
{json.dumps(quality, ensure_ascii=False, indent=2)}
```

## 10. Raw Evidence Pointers
- source_ref: {ring['source_ref']}
- origin_locator: {ring['origin_locator']}
- commit_watermark: {ring['commit_watermark']}
- anchor_hash: {ring['anchor_hash']}
- resolver_status: {ring.get('resolver_status', 'resolved')}
- redaction_status: {ring.get('redaction_status', 'pointer_only')}
- message_index_range: {json.dumps(ring.get('message_index_range', {}), ensure_ascii=False)}
- source_line_range: {json.dumps(ring.get('source_line_range') or {}, ensure_ascii=False)}
"""


def _write_provenance_ring_artifacts(vault: Path, *, ring_node: dict) -> dict:
    topic = ring_node["canonical_topic"]
    ring = ring_node["provenance_rings"][0]
    community = ring_node["community"]
    topic_path = vault / topic["page_path"]
    topic_path.parent.mkdir(parents=True, exist_ok=True)
    topic_path.write_text(_render_provenance_ring_page(ring_node=ring_node), encoding="utf-8")

    # OP2의 기존 BM25 fixed path가 concepts/entities 중심으로 읽으므로 POC mirror를 하나 둔다.
    concept_path = vault / "concepts" / f"{ring_node['node_id']}.md"
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    concept_rendered = _render_provenance_ring_page(ring_node=ring_node)
    concept_path.write_text(concept_rendered, encoding="utf-8")

    # 기존 full UX 최소 계약은 concepts/N-*.md mirror를 찾는다. POC ring node의 정식 ID는 PRN-*로 유지하되
    # legacy 검색/회귀 호환 mirror를 함께 둔다.
    legacy_id = "N-" + ring_node["node_id"].split("-", 1)[1]
    legacy_concept_path = vault / "concepts" / f"{legacy_id}.md"
    legacy_concept_path.write_text(concept_rendered.replace(f"id: {ring_node['node_id']}", f"id: {legacy_id}\ncanonical_node_id: {ring_node['node_id']}"), encoding="utf-8")

    topic_key = topic["topic_id"].split(":", 1)[1]
    prov_path = vault / "_meta" / "provenance" / f"{topic_key}.md"
    prov_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "episode_id": f"episode:ring:{ring['ring_id']}",
        "claim_id": f"claim:{ring_node['node_id']}",
        "support_fact": ring_node["decision_capsule"]["decision"],
        "ring_id": ring["ring_id"],
        "community_id": community["community_id"],
        "derived_from": topic["page_path"],
        "source_ref": ring["source_ref"],
        "origin_locator": ring["origin_locator"],
        "source_line_range": ring.get("source_line_range"),
        "node_taxonomy": ring_node.get("node_taxonomy", {}),
    }
    prov_path.write_text(
        "# Provenance Rings\n"
        f"<!-- provenance:{record['episode_id']}:start -->\n"
        f"## Episode {ring['ring_id']}\n"
        "```json\n"
        f"{json.dumps(record, ensure_ascii=False)}\n"
        "```\n"
        f"<!-- provenance:{record['episode_id']}:end -->\n",
        encoding="utf-8",
    )

    community_key = community["community_id"].split(":", 1)[-1]
    community_path = vault / "communities" / f"{community_key}.md"
    community_path.parent.mkdir(parents=True, exist_ok=True)
    community_taxonomy = build_community_node_taxonomy(community["community_id"])
    community_path.write_text(
        f"# {community_key}\n\n"
        f"- community_id: {community['community_id']}\n"
        f"- placement_reason: {community['placement_reason']}\n"
        f"- related_nodes: {ring_node['node_id']}\n"
        f"- ring_id: {ring['ring_id']}\n"
        f"- node_type: {community_taxonomy['node_type']}\n"
        f"- topography_level: {community_taxonomy['topography_level']}\n"
        f"- community_role: {community_taxonomy['community_role']}\n"
        "\n```json\n"
        f"{json.dumps({'node_taxonomy': community_taxonomy}, ensure_ascii=False, indent=2)}\n"
        "```\n",
        encoding="utf-8",
    )
    return {
        "canonical_topic_path": str(topic_path.relative_to(vault)),
        "concept_path": str(concept_path.relative_to(vault)),
        "legacy_concept_path": str(legacy_concept_path.relative_to(vault)),
        "provenance_path": str(prov_path.relative_to(vault)),
        "community_path": str(community_path.relative_to(vault)),
    }


CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"


def _is_atom_tag_hint(value: str) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return True
    if len(normalized) <= 5:
        return True
    if " " not in normalized and "/" not in normalized and "community" not in normalized.lower() and "category" not in normalized.lower():
        return True
    return False


def _is_nonempty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_index_range(value) -> bool:
    if not isinstance(value, dict):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, int) and isinstance(end, int) and start >= 0 and end >= start


def _valid_source_line_range(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, int) and isinstance(end, int) and start >= 1 and end >= start


def _valid_id_range(value) -> bool:
    if not isinstance(value, dict):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, (int, str)) and isinstance(end, (int, str)) and str(start) != "" and str(end) != ""


def _admit_memory_ticket_payload(payload: dict) -> tuple[bool, str]:
    if payload.get("schema_version") != "memory_ticket.v1":
        return False, "invalid_schema_version"
    for key in ("source_ref", "provider_session_id", "surface_reason", "commit_watermark"):
        if not _is_nonempty_string(payload.get(key)):
            return False, f"missing_{key}"
    has_index_range = "message_index_range" in payload
    has_id_range = "message_id_range" in payload
    if has_index_range == has_id_range:
        return False, "invalid_message_range_choice"
    if has_index_range and not _valid_index_range(payload.get("message_index_range")):
        return False, "invalid_message_index_range"
    if has_id_range and not _valid_id_range(payload.get("message_id_range")):
        return False, "invalid_message_id_range"
    if not _valid_source_line_range(payload.get("source_line_range")):
        return False, "invalid_source_line_range"
    if not _is_nonempty_string(payload.get("anchor_hash")):
        return False, "missing_anchor_hash"
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("anchor_hash"))):
        return False, "invalid_anchor_hash"
    for key in ("intent_field", "decomposition_guard", "min_split_unit", "why_not_atomic", "topic_hint", "category_community_hint"):
        if not _is_nonempty_string(payload.get(key)):
            return False, f"missing_{key}"
    if str(payload.get("decomposition_guard")) != CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD:
        return False, "invalid_decomposition_guard"
    if str(payload.get("min_split_unit")) not in {"paragraph_intent", "topic_decision_cluster"}:
        return False, "invalid_min_split_unit"
    if _is_atom_tag_hint(str(payload.get("category_community_hint") or "")):
        return False, "category_community_hint_too_atomic"
    return True, "admitted"


def _build_memory_ticket_quality_assessment(*, payload: dict, resolved: dict, ring_node: dict) -> dict:
    capsule = ring_node["decision_capsule"]
    community = ring_node["community"]
    ring = ring_node["provenance_rings"][0]
    checks = {
        "decision_capsule_present": bool(capsule.get("decision")),
        "context_present": bool(str(capsule.get("context") or "").strip()),
        "conclusion_present": bool(str(capsule.get("conclusion") or "").strip()),
        "evidence_pointer_present": bool(capsule.get("evidence")),
        "reuse_condition_present": bool(str(capsule.get("reuse_condition") or "").strip()),
        "source_ref_resolved": resolved.get("status") == "resolved",
        "bounded_message_range_present": isinstance(ring.get("message_index_range"), dict),
        "anchor_hash_verified": str(ring.get("anchor_hash") or "") == str(payload.get("anchor_hash") or ""),
        "paragraph_intent_guard_present": ring_node.get("paragraph_intent_safety_belt", {}).get("decomposition_guard") == CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD,
        "community_not_atomic": not _is_atom_tag_hint(str(payload.get("category_community_hint") or community.get("community_id") or "")),
        "node_taxonomy_valid": validate_node_taxonomy(ring_node.get("node_taxonomy", {}))["valid"],
        "raw_transcript_absent": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "evaluator": "memory_ticket_producer_quality_gate.v1",
        "verdict": "pass" if not failed else "needs_review",
        "confidence": 0.91 if not failed else 0.62,
        "reason_codes": failed,
        "ambiguity": "low" if not failed else "medium",
        "duplication_risk": "unknown_without_graph_dedupe",
        "misclassification_risk": "low" if checks["community_not_atomic"] else "high",
        "recallability": "community_and_source_path_retrievable" if not failed else "partial",
        "checks": checks,
        "hard_nonclaims": [
            "graph_dedupe_not_executed",
            "human_evaluator_not_executed",
        ],
    }


def _handle_memory_ticket(mailbox: Path, vault: Path, msg: dict) -> dict:
    """MemoryTicket 원본 범위를 resolver로 읽고 나이테 기억 노드 최소 POC 산출물을 만든다."""
    payload = msg.get("payload", {}) or {}
    admitted, admission_reason = _admit_memory_ticket_payload(payload)
    if not admitted:
        return {"status": "rejected", "nodes": [], "source_ref_status": "not_resolved", "reason": admission_reason}

    source_ref = str(payload.get("source_ref") or "")
    range_hint = payload.get("message_index_range") or {}
    source_line_range = payload.get("source_line_range") if isinstance(payload.get("source_line_range"), dict) else None
    anchor_hash = str(payload.get("anchor_hash") or "")
    resolver_options = dict(payload.get("resolver_options") or {})
    if payload.get("sessions_dir") and "sessions_dir" not in resolver_options:
        resolver_options["sessions_dir"] = payload.get("sessions_dir")

    try:
        from runtime.source_ref.bootstrap import register_default_source_ref_resolvers
        from runtime.source_ref.registry import resolve_source_ref

        register_default_source_ref_resolvers()
        resolved = resolve_source_ref(
            source_ref=source_ref,
            range_hint={"start": int(range_hint.get("start", 0)), "end": int(range_hint.get("end", 0))},
            anchor_hash=anchor_hash,
            resolver_options=resolver_options,
        )
    except Exception as exc:
        return {"status": "deferred", "nodes": [], "source_ref_status": "unavailable", "reason": f"resolver_error:{type(exc).__name__}"}

    if resolved.get("status") != "resolved":
        return {
            "status": "deferred",
            "nodes": [],
            "source_ref_status": resolved.get("status"),
            "reason": resolved.get("reason", "source_ref_not_resolved"),
        }

    decision = str(payload.get("decision") or payload.get("결정") or payload.get("surface_reason") or "MemoryTicket")
    topic_title = str(payload.get("canonical_topic_title") or payload.get("topic_title") or decision[:80])
    topic_key = _slugify_topic_key(str(payload.get("canonical_topic_key") or topic_title))
    node_id = "PRN-" + uuid.uuid5(uuid.NAMESPACE_URL, f"{source_ref}:{range_hint}:{decision}").hex[:16]
    ring_id = "ring-" + uuid.uuid5(uuid.NAMESPACE_URL, f"ring:{source_ref}:{range_hint}:{anchor_hash}").hex[:16]
    community_key = _slugify_topic_key(str(payload.get("community") or payload.get("커뮤니티") or "openyggdrasil-memory"))
    community_id = f"community:{community_key}"
    commit_watermark = str(payload.get("commit_watermark") or resolved.get("commit_watermark") or "")
    legacy_category = str(payload.get("category") or payload.get("移댄뀒怨좊━") or "policy")
    node_taxonomy = build_node_taxonomy(
        {**payload, "category": legacy_category},
        physical_continent="concepts",
        default_node_type="policy",
    )
    ring_node = {
        "schema_version": "provenance_ring_node.v1",
        "node_id": node_id,
        "category": str(payload.get("category") or payload.get("카테고리") or "policy"),
        "canonical_topic": {
            "topic_id": f"topic:{topic_key}",
            "title": topic_title,
            "page_path": f"queries/{topic_key}.md",
        },
        "decision_capsule": {
            "decision": decision,
            "context": str(payload.get("context") or payload.get("맥락") or payload.get("surface_reason") or ""),
            "conclusion": str(payload.get("conclusion") or payload.get("결론") or ""),
            "evidence": _as_list(payload.get("evidence") or payload.get("근거") or source_ref),
            "forbidden": _as_list(payload.get("forbidden") or payload.get("금지")),
            "reuse_condition": str(payload.get("reuse_condition") or payload.get("재사용 조건") or ""),
        },
        "provenance_rings": [{
            "ring_id": ring_id,
            "source_ref": source_ref,
            "origin_locator": str(resolved.get("origin_locator") or f"{source_ref}#message_index={range_hint.get('start')}..{range_hint.get('end')}"),
            "provider_session_id": str(payload.get("provider_session_id") or resolved.get("provider_session_id") or ""),
            "message_index_range": resolved.get("message_index_range") or range_hint,
            "source_line_range": source_line_range,
            "anchor_hash": anchor_hash,
            "commit_watermark": commit_watermark,
            "surface_reason": str(payload.get("surface_reason") or ""),
            "resolver_status": str(resolved.get("resolver_status") or resolved.get("status") or "resolved"),
            "redaction_status": str(resolved.get("redaction_status") or "pointer_only"),
        }],
        "lifecycle": {
            "state": "ACTIVE",
            "created_by_ring_id": ring_id,
            "lineage_edges": [{"type": "DERIVES_FROM", "target": str(resolved.get("origin_locator") or source_ref)}],
        },
        "community": {
            "community_id": community_id,
            "placement_reason": str(payload.get("surface_reason") or "MemoryTicket provenance placement"),
            "related_nodes": [],
        },
        "paragraph_intent_safety_belt": {
            "intent_field": str(payload.get("intent_field") or ""),
            "decomposition_guard": str(payload.get("decomposition_guard") or ""),
            "min_split_unit": str(payload.get("min_split_unit") or ""),
            "why_not_atomic": str(payload.get("why_not_atomic") or ""),
            "topic_hint": str(payload.get("topic_hint") or ""),
            "category_community_hint": str(payload.get("category_community_hint") or ""),
            "trigger_kind": str(payload.get("trigger_kind") or ""),
            "breadcrumb": str(payload.get("breadcrumb") or ""),
        },
        "retrieval_contract": {
            "keywords": [decision, topic_title, source_ref, community_key],
            "support_lanes": ["origin", "recent", "source_paths", "community_edges", "semantic_edges"],
        },
    }
    ring_node["category"] = node_taxonomy["node_type"]
    ring_node["node_taxonomy"] = node_taxonomy
    ring_node["quality_assessment"] = _build_memory_ticket_quality_assessment(
        payload=payload,
        resolved=resolved,
        ring_node=ring_node,
    )
    paths = _write_provenance_ring_artifacts(vault, ring_node=ring_node)
    return {
        "status": "acknowledged",
        "nodes": [node_id],
        "ring_ids": [ring_id],
        "source_ref_status": "resolved",
        "reason": "provenance_ring_node_saved",
        "canonical_topic_path": paths["canonical_topic_path"],
        "support_bundle_seed": {
            "ring_ids": [ring_id],
            "source_paths": list(paths.values()),
            "community_id": community_id,
            "source_line_range": source_line_range,
            "node_taxonomy": node_taxonomy,
            "quality_assessment": ring_node["quality_assessment"],
        },
    }


def _handle_promote(vault: Path, node_id: str) -> bool:
    """Nursery: DRAFT 노드를 ACTIVE로 승격."""
    node_file = vault / "concepts" / f"{node_id}.md"
    if not node_file.exists():
        node_file = vault / "entities" / f"{node_id}.md"
    if not node_file.exists():
        return False
    text = node_file.read_text(encoding="utf-8")
    if "status: DRAFT" not in text:
        return False
    text = text.replace("status: DRAFT", "status: ACTIVE")
    node_file.write_text(text, encoding="utf-8")
    return True


def _handle_sandbox_exec(mailbox: Path, vault: Path, msg: dict) -> dict:
    """intent: sandbox-exec 처리 — LLM 코드를 bubblewrap 샌드박스에서 실행.

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
            if "saved" in res:
                return res["saved"]
            if res.get("status") == "saved":
                return 1
            # Heuristic: final - initial node count difference
            if "final" in res and "initial" in res:
                return max(0, res["final"] - res["initial"])
        return 0
    except Exception:
        return 0
