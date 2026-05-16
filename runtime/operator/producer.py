"""
Operator Producer — 14차 Axis 3: operator_entrypoint.py에서 분리.

run_producer: Mailbox에서 save-intent를 폴링하여 Vault에 적재.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.log_event import log_event

from runtime.ptc.primitives import (
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
    write_operator_receipt,
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

try:
    from runtime.ptc.tool_search_supervisor import (
        build_memory_ticket_tst_supervisor,
        run_memory_saver_tst,
    )
except ImportError as exc:
    log_event("optional_import_unavailable", module="runtime.ptc.tool_search_supervisor", reason=str(exc))
    build_memory_ticket_tst_supervisor = None
    run_memory_saver_tst = None


def run_producer(mailbox: Path, vault: Path):
    """Mailbox에서 save-intent를 폴링하여 Vault에 적재."""
    t0 = datetime.now(timezone.utc)

    # ★ 14차 Axis 4: sandbox guard (보안 계층, 기능 블로커 아님)
    try:
        from runtime.sandbox import sandbox_run
        sandbox_ok = sandbox_run(["python3", "--version"], timeout=10)
        if sandbox_ok is None:
            log_event("sandbox_unavailable", reason="bwrap_not_found", action="continue_direct")
    except (ImportError, OSError, RuntimeError):
        log_event("sandbox_unavailable", reason="import_error", action="continue_direct")

    # POC Phase 0+: intents.jsonl 우선, legacy messages.jsonl 폴백
    messages_file = mailbox / "intents.jsonl"
    if not messages_file.exists():
        messages_file = mailbox / "messages.jsonl"
    receipts_file = mailbox / "receipts.jsonl"

    if not messages_file.exists():
        log_event("producer_no_messages")
        return

    # Load completed. A typed_unavailable close is not a durable save success and
    # must not permanently block a later role-owned processor retry.
    completed = set()
    if receipts_file.exists():
        for line in receipts_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("status") in {"acknowledged", "completed", "delivered"} and int(row.get("produced_count") or 0) > 0:
                    completed.add(row.get("in_reply_to"))

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
            tst_capability_supervisor = (
                build_memory_ticket_tst_supervisor(
                    payload=msg.get("payload", {}) or {},
                    result=result,
                )
                if build_memory_ticket_tst_supervisor is not None
                else None
            )
            worker_judgment = _memory_saver_judgment(
                intent="memory_ticket",
                status=status,
                nodes=nodes,
                reason=result.get("reason"),
                strict_storage_gate=(
                    (tst_capability_supervisor or {})
                    .get("result_summary", {})
                    .get("strict_storage_gate")
                ),
            )
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status=status,
                intent="memory_ticket",
                produced_count=len(nodes),
                nodes=nodes,
                ring_ids=ring_ids,
                canonical_topic_path=result.get("canonical_topic_path"),
                support_bundle_seed=result.get("support_bundle_seed"),
                source_ref_status=result.get("source_ref_status"),
                reason=result.get("reason"),
                tst_capability_supervisor=tst_capability_supervisor,
                worker_judgment=worker_judgment,
                producer_pid=os.getpid(),
            )
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
                    "tst_capability_supervisor": tst_capability_supervisor,
                    "worker_judgment": worker_judgment,
                },
            )
            continue

        # ★ 14차 Axis 4: sandbox-exec intent 처리 (PTC 코드 실행)
        if msg.get("intent") == "sandbox-exec":
            result = _handle_sandbox_exec(mailbox, vault, msg)
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status=result.get("status", "error"),
                intent="sandbox-exec",
                exit_code=result.get("exit_code"),
                sandbox=result.get("sandbox"),
                stdout=(result.get("stdout", "") or "")[:2000],
                stderr=(result.get("stderr", "") or "")[:2000],
            )
            continue

        # ★ Q13: prune intent 처리
        if msg.get("intent") == "prune":
            _handle_prune(mailbox, vault, msg)
            # Mark as completed
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status="acknowledged",
                intent="prune",
            )
            continue

        # ★ Q13: curate intent 처리 (curate→_handle_prune)
        if msg.get("intent") == "curate":
            _handle_prune(mailbox, vault, msg)
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status="acknowledged",
                intent="curate",
            )
            continue

        # ★ Q13: restore intent 처리 (restore→_restore_from_archive)
        if msg.get("intent") == "restore":
            node_id = msg.get("payload", {}).get("node_id", "")
            restored = _restore_from_archive(mailbox, vault, node_id)
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status="acknowledged",
                intent="restore",
                node_id=node_id,
                restored=restored,
            )
            continue

        # ★ Q13: skill_update intent 처리 (skill_update→_handle_skill_update)
        if msg.get("intent") == "skill_update":
            _handle_skill_update(mailbox, msg)
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status="acknowledged",
                intent="skill_update",
            )
            continue

        # Phase 2: PTC save path now goes through the role-scoped TST supervisor.
        # The old free-form code executor remains only as a compatibility fallback.
        if msg.get("payload", {}).get("ptc"):
            snapshot = msg.get("payload", {}).get("context_snapshot", "")
            if run_memory_saver_tst is not None:
                result = run_memory_saver_tst(
                    context_snapshot=snapshot,
                    vault_root=vault,
                    provider_id=msg.get("provider_id", "unknown"),
                )
                nodes = result.get("nodes") or []
                nodes_produced = int(result.get("produced_count") or 0)
                status = "acknowledged" if nodes_produced else "typed_unavailable"
                write_operator_receipt(
                    receipts_file,
                    msg["mail_id"],
                    status=status,
                    produced_count=nodes_produced,
                    nodes=nodes,
                    ptc_mode=True,
                    ptc_status=result.get("status"),
                    tst_supervisor=result.get("tst_supervisor"),
                    tst_capability_supervisor=(
                        result.get("tst_capability_supervisor")
                        or result.get("tst_supervisor")
                    ),
                    reason=result.get("status"),
                    worker_judgment=_memory_saver_judgment(
                        intent="save_ptc",
                        status=status,
                        nodes=nodes,
                        reason=result.get("status"),
                    ),
                )
                deliver_receipt(
                    mailbox,
                    msg["mail_id"],
                    status="delivered" if nodes_produced else "deferred",
                    produced_count=nodes_produced,
                    node_ids=nodes,
                    result_bundle={
                        "intent": "save",
                        "ptc_mode": True,
                        "tst_supervisor": result.get("tst_supervisor"),
                        "tst_capability_supervisor": (
                            result.get("tst_capability_supervisor")
                            or result.get("tst_supervisor")
                        ),
                        "reason": result.get("status"),
                    },
                )
            else:
                ptc_code = msg["payload"].get("ptc_code", "")
                if ptc_code.strip():
                    result = execute_ptc_code(
                        ptc_code,
                        vault,
                        mode="ipc",
                        timeout=120,
                        caller="memory_saver",
                    )
                    nodes_produced = _count_ptc_saves(result)
                    write_operator_receipt(
                        receipts_file,
                        msg["mail_id"],
                        status="acknowledged",
                        produced_count=nodes_produced,
                        ptc_mode=True,
                        ptc_stdout=(result.get("stdout", "") or "")[:500],
                        ptc_stderr=(result.get("stderr", "") or "")[:500],
                        ptc_status=result.get("status"),
                        ptc_exit=result.get("exit_code"),
                        worker_judgment=_memory_saver_judgment(
                            intent="save_ptc_compat",
                            status="acknowledged",
                            nodes=["ptc-save"] if nodes_produced else [],
                            reason=result.get("status"),
                        ),
                    )
                    deliver_receipt(mailbox, msg["mail_id"], status="delivered", produced_count=nodes_produced)
            continue
        # ★ Nursery: promote intent 처리 (DRAFT → ACTIVE)
        if msg.get("intent") == "promote":
            node_id = msg.get("payload", {}).get("node_id", "")
            if node_id:
                _handle_promote(vault, node_id)
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status="acknowledged",
                intent="promote",
                node_id=node_id,
            )
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
                    write_operator_receipt(
                        receipts_file,
                        msg["mail_id"],
                        status="rejected",
                        reason=reason,
                        gate="admission_gate.v1",
                    )
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

        write_operator_receipt(
            receipts_file,
            msg["mail_id"],
            status="acknowledged",
            produced_count=len(nodes),
            nodes=nodes,
            worker_judgment=_memory_saver_judgment(
                intent="save",
                status="acknowledged",
                nodes=nodes,
            ),
            producer_pid=os.getpid(),
        )

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


def _memory_saver_judgment(
    *,
    intent: str,
    status: str,
    nodes: list,
    reason: object = None,
    strict_storage_gate: dict | None = None,
) -> dict:
    """Provider-safe worker judgment summary for MS receipts."""
    produced_count = len(nodes or [])
    strict_allowed = (
        strict_storage_gate.get("storage_success_allowed")
        if isinstance(strict_storage_gate, dict)
        else None
    )
    success = status in {"acknowledged", "completed"} and produced_count > 0
    if strict_allowed is False:
        success = False
    return {
        "schema_version": "worker_judgment.v1",
        "worker_role": "memory_saver",
        "small_goal": (
            "decide whether the Save Request has enough durable evidence to become stored memory"
        ),
        "todo": [
            "check source and intent evidence",
            "run the role-scoped save/provenance path",
            "inspect produced node and receipt evidence",
            "close as storage_receipt or typed_unavailable",
        ],
        "success_evidence": [
            "produced_count > 0",
            "node ids are present",
            "Result Receipt was written",
        ],
        "failure_conditions": [
            "no durable save candidate",
            "source/provenance evidence missing",
            "produced_count is zero",
            "requested and saved cannot be distinguished",
        ],
        "observation": {
            "intent": intent,
            "status": status,
            "produced_count": produced_count,
            "node_count": len(nodes or []),
            "reason": str(reason or ""),
            "strict_storage_gate_allowed": strict_allowed,
            "strict_storage_gate_failure_reason": (
                strict_storage_gate.get("failure_reason")
                if isinstance(strict_storage_gate, dict)
                else None
            ),
        },
        "judgment": "success" if success else "typed_unavailable",
        "close_decision": "storage_receipt" if success else "typed_unavailable_no_storage_evidence",
        "hard_nonclaims": [
            "delivery_is_not_storage_success",
            "pane_text_is_not_storage_success",
            "storage_receipt_is_not_semantic_truth",
        ],
    }

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
    except (ImportError, OSError, ValueError, TypeError):
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
    rings = list(ring_node["provenance_rings"] or [])
    ring = rings[-1]
    source_refs = []
    for item in rings:
        source_ref = str(item.get("source_ref") or "").strip()
        if source_ref and source_ref not in source_refs:
            source_refs.append(source_ref)
    lifecycle = ring_node["lifecycle"]
    community = ring_node["community"]
    taxonomy = ring_node.get("node_taxonomy", {})
    retrieval = ring_node["retrieval_contract"]
    safety_belt = ring_node.get("paragraph_intent_safety_belt", {})
    quality = ring_node.get("quality_assessment", {})
    retrieval_terms = retrieval.get("retrieval_terms") or retrieval.get("keywords") or []
    quality_verdict = str(quality.get("verdict") or "").lower()
    lifecycle_state = "ACTIVE" if quality_verdict == "pass" else "NEEDS_REPAIR"
    current_authority = "active" if quality_verdict == "pass" else "candidate_only"
    return f"""---
id: {ring_node['node_id']}
title: {topic['title']}
type: {ring_node.get('category', 'policy')}
continent: {taxonomy.get('continent', 'concepts')}
physical_continent: {taxonomy.get('physical_continent', 'concepts')}
node_type: {taxonomy.get('node_type', ring_node.get('category', 'policy'))}
topography_level: {taxonomy.get('topography_level', 'tree')}
community_role: {taxonomy.get('community_role', 'member')}
status: {lifecycle_state}
community: {community['community_id']}
sources: [{', '.join(source_refs)}]
root_claim: {capsule['decision']}
current_authority: {current_authority}
ring_id: {ring['ring_id']}
lifecycle_state: {lifecycle_state}
---
# {topic['title']}

## What This Page Is
This page records a reusable knowledge candidate with provenance and recall boundaries.

## Why It Matters
It keeps the decision, source range, community placement, and recall surface together so later vague questions can be answered without inventing context.

## Operating Rule
{capsule['decision']}

## Role Boundary
Provider rejudges returned support; MS1 stores only admitted source-backed candidates; MF1 recalls only safe indexed evidence.

## Failure Cases
- missing or unresolved source_ref
- pending candidate treated as final support
- local path or pane text treated as proof

## Examples
- Use this when a later question asks for the same boundary in different words.
- If the page is still `NEEDS_REPAIR`, treat it as a candidate until janitor and recall gates admit it.

## Source Synthesis
- source_ref: {ring['source_ref']}
- origin_locator: {ring['origin_locator']}
- community: {community['community_id']}
- maturity: {lifecycle_state}

## Retrieval Surface
- keyword_policy: {retrieval.get('keyword_policy', 'deterministic_diverse_terms_not_title_repeat')}
- retrieval_terms: {', '.join(str(item) for item in retrieval_terms)}

## Related Pages
{_render_related_pages(community)}

## Maintenance Notes
- quality_verdict: {quality.get('verdict', 'unknown')}
- reason_codes: {', '.join(str(item) for item in quality.get('reason_codes') or [])}
- confidence: {quality.get('confidence', 'unknown')}

## Machine Appendix

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


def _render_related_pages(community: dict) -> str:
    related_nodes = _as_list(community.get("related_nodes"))
    if not related_nodes:
        return "- related pages are not established yet; janitor must backfill or keep this candidate out of final support."
    return "\n".join(f"- {node_id}" for node_id in related_nodes)


def _retrieval_terms_from_payload(*, payload: dict, decision: str, topic_title: str, community_key: str) -> list[str]:
    candidates = [
        decision,
        topic_title,
        community_key.replace("-", " "),
        str(payload.get("topic_hint") or ""),
        str(payload.get("category_community_hint") or ""),
        str(payload.get("breadcrumb") or ""),
        str(payload.get("reuse_condition") or ""),
        "wiki ring",
        "source-backed",
        "safe recall",
        "MS storage",
        "MF recall boundary",
        "provenance",
    ]
    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = re.sub(r"\s+", " ", str(candidate or "").strip().lower())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
        if len(terms) >= 16:
            break
    return terms


def _merge_unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _source_refs_from_related_nodes(vault: Path, related_nodes: list[str]) -> list[str]:
    refs: list[str] = []
    for node_id in related_nodes:
        node = str(node_id or "").strip()
        if not node:
            continue
        path = vault / "concepts" / f"{node}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        refs.extend(re.findall(r"hermes-session-json://[A-Za-z0-9_\-]+", text))
    return _merge_unique_values(refs)


def _community_growth_events(*, ring_ids: list[str], source_refs: list[str]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for index, source_ref in enumerate(source_refs):
        event = {"source_ref": source_ref}
        if index < len(ring_ids):
            event["ring_id"] = ring_ids[index]
        events.append(event)
    return events


def _write_provenance_ring_artifacts(vault: Path, *, ring_node: dict) -> dict:
    topic = ring_node["canonical_topic"]
    ring = ring_node["provenance_rings"][0]
    community = ring_node["community"]
    topic_path = vault / topic["page_path"]
    topic_path.parent.mkdir(parents=True, exist_ok=True)
    existing_topic = topic_path.read_text(encoding="utf-8") if topic_path.exists() else ""
    merged_rings = _merge_provenance_rings(
        _existing_provenance_rings(existing_topic),
        list(ring_node["provenance_rings"] or []),
    )
    if merged_rings:
        ring_node = {**ring_node, "provenance_rings": merged_rings}
    ring = ring_node["provenance_rings"][-1]
    topic_path.write_text(_render_provenance_ring_page(ring_node=ring_node), encoding="utf-8")

    # MF1 BM25 fixed path reads concepts/entities first, so keep one canonical concept mirror.
    concept_path = vault / "concepts" / f"{ring_node['node_id']}.md"
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    concept_rendered = _render_provenance_ring_page(ring_node=ring_node)
    concept_path.write_text(concept_rendered, encoding="utf-8")

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
    episode_block = (
        f"<!-- provenance:{record['episode_id']}:start -->\n"
        f"## Episode {ring['ring_id']}\n"
        "```json\n"
        f"{json.dumps(record, ensure_ascii=False)}\n"
        "```\n"
        f"<!-- provenance:{record['episode_id']}:end -->\n"
    )
    existing_provenance = prov_path.read_text(encoding="utf-8") if prov_path.exists() else "# Provenance Rings\n"
    if f"provenance:{record['episode_id']}:start" not in existing_provenance:
        existing_provenance = existing_provenance.rstrip() + "\n" + episode_block
    prov_path.write_text(existing_provenance, encoding="utf-8")

    community_key = community["community_id"].split(":", 1)[-1]
    community_path = vault / "communities" / f"{community_key}.md"
    community_path.parent.mkdir(parents=True, exist_ok=True)
    community_taxonomy = build_community_node_taxonomy(community["community_id"])
    existing_community = community_path.read_text(encoding="utf-8") if community_path.exists() else ""
    related_nodes = _merge_metadata_values(existing_community, "related_nodes", [ring_node["node_id"]])
    ring_ids = _merge_metadata_values(existing_community, "ring_ids", [ring["ring_id"]])
    ring_ids = _merge_metadata_values(existing_community, "ring_id", ring_ids)
    source_refs = _merge_unique_values(
        [
            *_metadata_values(existing_community, "source_refs"),
            *_source_refs_from_related_nodes(vault, related_nodes),
            ring["source_ref"],
        ]
    )
    growth_events = _community_growth_events(ring_ids=ring_ids, source_refs=source_refs)
    community_path.write_text(
        f"# {community_key}\n\n"
        f"- community_id: {community['community_id']}\n"
        f"- placement_reason: {community['placement_reason']}\n"
        f"- growth_policy: append_only_discontinuous_source_ref\n"
        f"- growth_event_count: {len(source_refs)}\n"
        f"- related_nodes: {', '.join(related_nodes)}\n"
        f"- ring_id: {ring['ring_id']}\n"
        f"- ring_ids: {', '.join(ring_ids)}\n"
        f"- source_refs: {', '.join(source_refs)}\n"
        f"- overmerge_guard: split_when_new_source_ref_changes_runtime_category\n"
        f"- node_type: {community_taxonomy['node_type']}\n"
        f"- topography_level: {community_taxonomy['topography_level']}\n"
        f"- community_role: {community_taxonomy['community_role']}\n"
        "\n```json\n"
        f"{json.dumps({'schema_version': 'community_growth_history.v1', 'node_taxonomy': community_taxonomy, 'growth_events': growth_events}, ensure_ascii=False, indent=2)}\n"
        "```\n",
        encoding="utf-8",
    )
    return {
        "canonical_topic_path": str(topic_path.relative_to(vault)),
        "concept_path": str(concept_path.relative_to(vault)),
        "provenance_path": str(prov_path.relative_to(vault)),
        "community_path": str(community_path.relative_to(vault)),
    }


def _write_safe_index_cursor_sync(vault: Path, *, ring_id: str, paths: dict) -> dict:
    committed_paths = [value for value in paths.values() if value]
    try:
        from runtime.retrieval.safe_index_cursor import (
            SAFE_INDEX_CURSOR_RELATIVE_PATH,
            load_safe_index_cursor,
            write_safe_index_cursor,
        )

        existing_cursor = load_safe_index_cursor(vault)
        existing_committed_paths = list(existing_cursor.get("committed_paths") or [])
        cursor_path = write_safe_index_cursor(
            vault_root=vault,
            committed_paths=[*existing_committed_paths, *committed_paths],
            cursor_id=f"cursor:{ring_id}",
            source="memory_ticket_producer",
        )
        cursor = load_safe_index_cursor(vault)
        return {
            "schema_version": "safe_index_cursor_sync.v1",
            "janitor_status": "clean",
            "cursor_path": str(cursor_path.relative_to(vault)).replace("\\", "/")
            if cursor_path.is_absolute()
            else SAFE_INDEX_CURSOR_RELATIVE_PATH,
            "committed_paths": list(cursor.get("committed_paths") or []),
            "hard_nonclaims": [
                "safe_cursor_sync_is_not_semantic_truth",
                "safe_cursor_sync_is_not_full_vault_consistency",
            ],
        }
    except Exception as exc:
        return {
            "schema_version": "safe_index_cursor_sync.v1",
            "janitor_status": "issues_detected",
            "committed_paths": [f"vault/{str(path).replace('\\', '/').lstrip('/')}" for path in committed_paths],
            "reason_code": f"safe_index_cursor_sync_failed:{type(exc).__name__}",
            "hard_nonclaims": [
                "failed_safe_cursor_sync_does_not_authorize_final_support",
            ],
        }


CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"


def _metadata_values(text: str, key: str) -> list[str]:
    match = re.search(rf"^\s*-\s*{re.escape(key)}\s*:\s*(.*?)\s*$", text or "", flags=re.MULTILINE)
    if not match:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def _existing_provenance_rings(text: str) -> list[dict]:
    match = re.search(r"## 3\. Provenance Rings\s*```json\s*(.*?)\s*```", text or "", flags=re.DOTALL)
    if not match:
        return []
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict) and item.get("ring_id")]
    return []


def _merge_provenance_rings(*ring_lists: list[dict]) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for rings in ring_lists:
        for ring in rings:
            ring_id = str(ring.get("ring_id") or "").strip()
            if not ring_id or ring_id in seen:
                continue
            seen.add(ring_id)
            merged.append(dict(ring))
    return merged


def _merge_metadata_values(text: str, key: str, values: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in [*_metadata_values(text, key), *values]:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


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
    for key in ("decision", "context", "conclusion", "reuse_condition"):
        if not _is_nonempty_string(payload.get(key)):
            return False, "missing_decision_capsule"
    return True, "admitted"


def _build_memory_ticket_quality_assessment(*, payload: dict, resolved: dict, ring_node: dict) -> dict:
    capsule = ring_node["decision_capsule"]
    community = ring_node["community"]
    ring = ring_node["provenance_rings"][0]
    evidence_refs = _as_list(capsule.get("evidence"))
    external_evidence_refs = [
        ref
        for ref in evidence_refs
        if not str(ref).startswith("hermes-session-json://")
    ]
    related_nodes = _as_list(community.get("related_nodes"))
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
        "external_source_synthesis_present": bool(external_evidence_refs),
        "related_nodes_present": bool(related_nodes),
    }
    failed = [name for name, passed in checks.items() if not passed]
    reason_codes = list(failed)
    if str(payload.get("human_evaluator_status") or "").lower() != "executed":
        reason_codes.append("human_evaluator_not_executed")
    if str(payload.get("graph_dedupe_status") or "").lower() != "executed":
        reason_codes.append("graph_dedupe_not_executed")
    verdict = "pass" if not reason_codes else "needs_review"
    confidence = 0.91 if verdict == "pass" else 0.72
    return {
        "evaluator": "memory_ticket_producer_quality_gate.v1",
        "verdict": verdict,
        "confidence": confidence,
        "reason_codes": reason_codes,
        "ambiguity": "low" if verdict == "pass" else "medium",
        "duplication_risk": "unknown_without_graph_dedupe",
        "misclassification_risk": "low" if checks["community_not_atomic"] else "high",
        "recallability": "community_and_source_path_retrievable" if verdict == "pass" else "candidate_only",
        "checks": checks,
        "hard_nonclaims": [
            *([] if str(payload.get("graph_dedupe_status") or "").lower() == "executed" else ["graph_dedupe_not_executed"]),
            *([] if str(payload.get("human_evaluator_status") or "").lower() == "executed" else ["human_evaluator_not_executed"]),
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
    if payload.get("evidence") and "evidence" not in resolver_options:
        resolver_options["evidence"] = payload.get("evidence")

    try:
        from runtime.source_ref.bootstrap import register_default_source_ref_resolvers
        from runtime.source_ref.registry import resolve_source_ref

        register_default_source_ref_resolvers()
        resolver_range_hint = {"start": int(range_hint.get("start", 0)), "end": int(range_hint.get("end", 0))}
        if source_line_range:
            resolver_range_hint["source_line_range"] = dict(source_line_range)
        resolved = resolve_source_ref(
            source_ref=source_ref,
            range_hint=resolver_range_hint,
            anchor_hash=anchor_hash,
            resolver_options=resolver_options,
        )
    except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
        return {"status": "deferred", "nodes": [], "source_ref_status": "unavailable", "reason": f"resolver_error:{type(exc).__name__}"}

    if resolved.get("status") != "resolved":
        return {
            "status": "deferred",
            "nodes": [],
            "source_ref_status": resolved.get("status"),
            "reason": resolved.get("reason", "source_ref_not_resolved"),
        }

    decision = str(payload.get("decision") or payload.get("결정") or payload.get("surface_reason") or "MemoryTicket")
    topic_title = str(payload.get("canonical_topic_title") or payload.get("topic_title") or decision)
    topic_key = _slugify_topic_key(str(payload.get("canonical_topic_key") or topic_title))
    node_id = "N-" + uuid.uuid5(uuid.NAMESPACE_URL, f"{source_ref}:{range_hint}:{decision}").hex[:16]
    ring_id = "ring-" + uuid.uuid5(uuid.NAMESPACE_URL, f"ring:{source_ref}:{range_hint}:{anchor_hash}").hex[:16]
    community_key = _slugify_topic_key(str(payload.get("community") or payload.get("커뮤니티") or "openyggdrasil-memory"))
    community_id = f"community:{community_key}"
    commit_watermark = str(payload.get("commit_watermark") or resolved.get("commit_watermark") or "")
    retrieval_terms = _retrieval_terms_from_payload(
        payload=payload,
        decision=decision,
        topic_title=topic_title,
        community_key=community_key,
    )
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
            "related_nodes": _as_list(payload.get("related_nodes") or payload.get("related_pages")),
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
            "retrieval_terms": retrieval_terms,
            "keyword_policy": "deterministic_diverse_terms_not_title_repeat",
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
    quality_verdict = str(ring_node["quality_assessment"].get("verdict") or "")
    if quality_verdict != "pass":
        return {
            "status": "typed_unavailable",
            "nodes": [],
            "ring_ids": [],
            "source_ref_status": "resolved",
            "reason": "quality_assessment_not_pass",
            "quality_assessment": ring_node["quality_assessment"],
            "support_bundle_seed": {
                "ring_ids": [],
                "source_paths": [],
                "community_id": community_id,
                "source_line_range": source_line_range,
                "node_taxonomy": node_taxonomy,
                "quality_assessment": ring_node["quality_assessment"],
                "safe_index_cursor_sync": {
                    "schema_version": "safe_index_cursor_sync.v1",
                    "janitor_status": "blocked",
                    "committed_paths": [],
                    "reason_code": "quality_assessment_not_pass",
                    "hard_nonclaims": [
                        "candidate_node_not_safe_final_support",
                        "needs_review_node_not_committed_to_safe_index_cursor",
                    ],
                },
            },
        }
    paths = _write_provenance_ring_artifacts(vault, ring_node=ring_node)
    safe_index_cursor_sync = _write_safe_index_cursor_sync(vault, ring_id=ring_id, paths=paths)
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
            "safe_index_cursor_sync": safe_index_cursor_sync,
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
    result = execute_ptc_code(code, vault, timeout=timeout, caller="memory_saver")
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
            caller="memory_saver",
            allowed_methods=("suggest_placement",),
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
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    except (OSError, RuntimeError, ValueError, TypeError):
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
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0
