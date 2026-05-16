from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping






_WORD_RE = re.compile(r"[A-Za-z0-9_\uac00-\ud7a3][A-Za-z0-9_.:\uac00-\ud7a3-]{1,}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _latest_work_order(mailbox: Path, mail_id: str) -> dict[str, Any]:
    for row in reversed(_read_jsonl(mailbox / "work_orders.jsonl")):
        if row.get("mail_id") == mail_id:
            return row
    return {}


def _tokens(text: str) -> set[str]:
    tokens = {match.group(0).lower() for match in _WORD_RE.finditer(text or "")}
    expanded = set(tokens)
    alias_groups = [
        {"agent", "agents", "에이전트"},
        {"plugin", "plugins", "플러그인"},
        {"subagent", "subagents", "서브에이전트"},
        {"team", "teams", "팀"},
        {"hook", "hooks", "훅"},
        {"skill", "skills", "스킬"},
        {"mcp"},
        {"execution", "runtime", "실행"},
        {"model", "models", "모델"},
        {"definition", "defined", "정의"},
        {"supply", "source", "path", "공급", "공급원", "경로"},
        {"placement", "axis", "axes", "배치", "축"},
        {"automatic", "event", "자동", "이벤트"},
        {"procedure", "rubric", "judgment", "절차", "판단", "기준"},
        {"external", "connection", "connect", "외부", "연결"},
        {"distribution", "package", "packaging", "배포", "패키지", "묶음"},
    ]
    for token in list(tokens):
        for group in alias_groups:
            if token in group or any(item and item in token for item in group):
                expanded.update(group)
    return expanded


def _high_specificity_tokens(text: str) -> set[str]:
    return {
        token
        for token in _tokens(text)
        if any(ch.isdigit() for ch in token) or "_" in token or len(token) >= 24
    }


def _support_facts_and_paths(result_bundle: Mapping[str, Any] | None) -> tuple[list[Any], list[Any]]:
    if not isinstance(result_bundle, Mapping):
        return [], []
    nested = result_bundle.get("support_bundle") if isinstance(result_bundle.get("support_bundle"), Mapping) else {}
    facts = result_bundle.get("support_facts") or nested.get("support_facts") or []
    paths = result_bundle.get("source_paths") or nested.get("source_paths") or []
    return (
        list(facts) if isinstance(facts, list) else [],
        list(paths) if isinstance(paths, list) else [],
    )


def _fact_text(fact: Any) -> str:
    if isinstance(fact, Mapping):
        return " ".join(
            str(part).strip()
            for part in [
                fact.get("subject"),
                fact.get("predicate"),
                fact.get("object"),
                fact.get("summary"),
                fact.get("text"),
            ]
            if str(part or "").strip()
        )
    return str(fact or "")


def _support_text(result_bundle: Mapping[str, Any] | None) -> str:
    facts, paths = _support_facts_and_paths(result_bundle)
    return "\n".join([*(_fact_text(fact) for fact in facts), *(str(path) for path in paths)])


def _selected_capabilities(result_bundle: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result_bundle, Mapping):
        return []
    candidates = [
        result_bundle.get("tst_capability_supervisor"),
        (result_bundle.get("ptc_worker_program") or {}).get("tst_capability_supervisor")
        if isinstance(result_bundle.get("ptc_worker_program"), Mapping)
        else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            selected = candidate.get("selected_capabilities")
            if isinstance(selected, list):
                return [
                    {
                        "capability_id": row.get("capability_id") or row.get("tool_id"),
                        "tool_id": row.get("tool_id"),
                        "adapter_status": row.get("adapter_status"),
                        "capability_family": row.get("capability_family"),
                    }
                    for row in selected
                    if isinstance(row, Mapping)
                ]
    return []


def _typed_unavailable(result_bundle: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result_bundle, Mapping):
        return None
    for value in [result_bundle.get("typed_unavailable")]:
        if isinstance(value, Mapping):
            return dict(value)
    if result_bundle.get("support_facts") and result_bundle.get("source_paths"):
        return None
    nested = result_bundle.get("support_bundle")
    if isinstance(nested, Mapping) and isinstance(nested.get("typed_unavailable"), Mapping):
        return dict(nested["typed_unavailable"])
    return None


def _worker_ptc_contracts(result_bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result_bundle, Mapping):
        return {}
    candidates = [
        result_bundle.get("tst_capability_supervisor"),
        (result_bundle.get("ptc_worker_program") or {}).get("tst_capability_supervisor")
        if isinstance(result_bundle.get("ptc_worker_program"), Mapping)
        else None,
    ]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        return {
            "schema_version": "worker_ptc_contracts_summary.v1",
            "worker_authored_ptc_program": candidate.get("worker_authored_ptc_program"),
            "ptc_program_review": candidate.get("ptc_program_review"),
            "tst_capability_allowlist": candidate.get("tst_capability_allowlist"),
            "ptc_program_observation": candidate.get("ptc_program_observation"),
            "observation_delta_gate": candidate.get("observation_delta_gate"),
        }
    return {}


def _fallback_worker_judgment(
    *,
    worker_role: str,
    status: str,
    produced_count: int,
    node_ids: list[str],
    result_bundle: Mapping[str, Any] | None,
) -> dict[str, Any]:
    facts, paths = _support_facts_and_paths(result_bundle)
    if worker_role == "memory_saver":
        success = status in {"acknowledged", "completed", "delivered"} and (produced_count > 0 or bool(node_ids))
        return {
            "schema_version": "worker_judgment.v1",
            "worker_role": "memory_saver",
            "judgment": "success" if success else "typed_unavailable",
            "close_decision": "storage_receipt" if success else "typed_unavailable_no_storage_evidence",
        }
    success = status in {"completed", "delivered"} and bool(facts) and bool(paths)
    return {
        "schema_version": "worker_judgment.v1",
        "worker_role": "memory_finder",
        "judgment": "success" if success else "typed_unavailable",
        "close_decision": "support_bundle" if success else "typed_unavailable_no_support",
    }


def _worker_role_from_mailbox(mailbox: Path) -> str:
    name = mailbox.name.upper()
    if name.startswith("OP"):
        try:
            index = int(name[2:])
        except ValueError:
            return "unknown"
        return "memory_saver" if index % 2 == 1 else "memory_finder"
    lowered = mailbox.name.lower()
    if "mf" in lowered or "finder" in lowered:
        return "memory_finder"
    if "ms" in lowered or "saver" in lowered:
        return "memory_saver"
    return "unknown"


def _work_order_anchor(work_order: Mapping[str, Any]) -> dict[str, Any]:
    anchor = work_order.get("work_anchor")
    if isinstance(anchor, Mapping) and anchor.get("schema_version") == "provider_work_anchor.v1":
        return dict(anchor)
    summary = work_order.get("work_summary")
    if isinstance(summary, str):
        return {
            "schema_version": "provider_work_anchor.v1",
            "anchor_kind": "user_question" if summary else "missing_anchor",
            "anchor_text": summary,
            "user_question_present": bool(summary),
            "provider_initiated_need_present": False,
            "hard_nonclaims": [
                "legacy_work_summary_anchor_needs_upgrade",
            ],
        }
    payload_ref = work_order.get("payload_ref")
    if isinstance(payload_ref, Mapping):
        text = " ".join(str(payload_ref.get(key) or "") for key in ["mail_id", "kind"])
        return {
            "schema_version": "provider_work_anchor.v1",
            "anchor_kind": "missing_anchor",
            "anchor_text": text,
            "user_question_present": False,
            "provider_initiated_need_present": False,
            "hard_nonclaims": [
                "payload_ref_identifier_is_not_semantic_question_anchor",
            ],
        }
    return {
        "schema_version": "provider_work_anchor.v1",
        "anchor_kind": "missing_anchor",
        "anchor_text": "",
        "user_question_present": False,
        "provider_initiated_need_present": False,
        "hard_nonclaims": [
            "no_user_question_or_provider_need_anchor_present",
        ],
    }


def _alignment_state(*, user_question: str, result_bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    support_text = _support_text(result_bundle)
    question_tokens = _tokens(user_question)
    support_tokens = _tokens(support_text)
    high_specificity = _high_specificity_tokens(user_question)
    overlap = sorted(question_tokens & support_tokens)
    missing_specific = sorted(token for token in high_specificity if token not in support_tokens)
    score = 0.0 if not question_tokens else len(overlap) / max(len(question_tokens), 1)
    if missing_specific:
        state = "misaligned"
    elif score >= 0.15 or (high_specificity and not missing_specific):
        state = "aligned"
    elif support_tokens:
        state = "insufficient_context"
    else:
        state = "no_support"
    return {
        "schema_version": "provider_question_alignment.v1",
        "state": state,
        "query_alignment_score": round(score, 4),
        "overlap_count": len(overlap),
        "high_specificity_tokens_checked": sorted(high_specificity),
        "missing_high_specificity_tokens": missing_specific,
    }


def build_provider_rejudgment(
    *,
    worker_result_spec: Mapping[str, Any],
    user_question: str | None = None,
) -> dict[str, Any]:
    """Provider-side meta judgment over an MF/MS result spec.

    The Provider must not treat MF support as authority. This result tells the
    Provider whether to use the support, ask the user to clarify, or send a
    counter-reply to the worker/Postman ledger.
    """

    worker_role = str(worker_result_spec.get("worker_role") or "")
    anchor = worker_result_spec.get("provider_work_anchor")
    if not isinstance(anchor, Mapping):
        anchor = {
            "schema_version": "provider_work_anchor.v1",
            "anchor_kind": "user_question" if worker_result_spec.get("provider_question") else "missing_anchor",
            "anchor_text": str(worker_result_spec.get("provider_question") or ""),
            "user_question_present": bool(worker_result_spec.get("provider_question")),
            "provider_initiated_need_present": False,
        }
    anchor_kind = str(anchor.get("anchor_kind") or "missing_anchor")
    question = user_question or str(anchor.get("anchor_text") or worker_result_spec.get("provider_question") or "")
    result_bundle = worker_result_spec.get("support_bundle")
    if not isinstance(result_bundle, Mapping):
        result_bundle = {}
    alignment = _alignment_state(user_question=question, result_bundle=result_bundle)
    typed_unavailable = worker_result_spec.get("typed_unavailable")
    if worker_role != "memory_finder":
        action = "acknowledge_storage_receipt"
        reason_code = "storage_result_not_answer_authority"
    elif anchor_kind == "missing_anchor":
        action = "ask_user_clarification"
        reason_code = "missing_user_question_or_provider_need_anchor"
    elif typed_unavailable and anchor_kind == "user_question":
        action = "ask_user_clarification"
        reason_code = "worker_returned_typed_unavailable"
    elif typed_unavailable:
        action = "reply_to_worker_reject"
        reason_code = "provider_initiated_need_not_satisfied"
    elif alignment["state"] == "aligned":
        action = "use_with_limits"
        reason_code = "support_aligned_with_work_anchor"
    elif alignment["state"] == "insufficient_context" and anchor_kind == "user_question":
        action = "ask_user_clarification"
        reason_code = "support_context_insufficient_for_user_question"
    elif alignment["state"] == "insufficient_context":
        action = "reply_to_worker_reject"
        reason_code = "support_context_insufficient_for_provider_initiated_need"
    else:
        action = "reply_to_worker_reject"
        reason_code = "support_misaligned_with_work_anchor"
    return {
        "schema_version": "provider_result_rejudgment.v1",
        "created_at": _now_iso(),
        "provider_trust_policy": "do_not_trust_worker_result_without_question_alignment",
        "provider_work_anchor": dict(anchor),
        "provider_action": action,
        "reason_code": reason_code,
        "question_alignment": alignment,
        "counter_reply_to_worker": {
            "schema_version": "provider_worker_counter_reply.v1",
            "enabled": action == "reply_to_worker_reject",
            "target_worker_role": worker_role,
            "reason_code": reason_code,
            "request": "retry_with_user_question_alignment_or_return_typed_unavailable",
        },
        "clarification_request": {
            "schema_version": "provider_user_clarification_request.v1",
            "enabled": action == "ask_user_clarification",
            "reason_code": reason_code,
            "question": "어떤 이전 맥락을 기준으로 찾을지 한 단서만 더 알려주세요.",
        },
        "hard_nonclaims": [
            "mf_result_is_not_provider_answer_authority",
            "provider_must_compare_support_to_user_question_or_provider_need",
            "similar_support_is_not_aligned_support",
            "missing_user_question_can_be_valid_provider_initiated_memory_work",
        ],
    }


def build_worker_result_spec(
    mailbox: Path,
    mail_id: str,
    *,
    status: str,
    result_bundle: dict[str, Any] | None = None,
    produced_count: int = 0,
    node_ids: list[str] | None = None,
    worker_judgment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Postman-facing worker result spec.

    This is the result contract returned from MS/MF to Postman. Pane text is a
    projection only; this spec is what Postman and Provider-side consumers read.
    """

    mailbox = Path(mailbox)
    nodes = list(node_ids or [])
    work_order = _latest_work_order(mailbox, mail_id)
    bundle = dict(result_bundle or {})
    facts, paths = _support_facts_and_paths(bundle)
    worker_role = str(work_order.get("worker_role") or _worker_role_from_mailbox(mailbox))
    if worker_role == "unknown":
        worker_role = "memory_finder" if facts or paths or isinstance(bundle.get("support_bundle"), Mapping) else "memory_saver"
    judgment = dict(
        worker_judgment
        or bundle.get("worker_judgment")
        or _fallback_worker_judgment(
            worker_role=worker_role,
            status=status,
            produced_count=produced_count,
            node_ids=nodes,
            result_bundle=bundle,
        )
    )
    typed_unavailable = _typed_unavailable(bundle)
    result_kind = "storage_evidence" if worker_role == "memory_saver" else "support_bundle"
    if typed_unavailable or (worker_role == "memory_finder" and not (facts and paths)):
        result_kind = "typed_unavailable"
    if worker_role == "memory_saver" and not (produced_count or nodes):
        result_kind = "typed_unavailable"
    postman_acceptance_status = (
        "accepted_for_provider_rejudgment"
        if result_kind in {"storage_evidence", "support_bundle"}
        else "accepted_as_typed_unavailable"
    )
    evidence_refs: list[dict[str, Any]] = []
    if nodes:
        evidence_refs.append({"kind": "node_ids", "count": len(nodes), "digest": _digest(nodes)})
    if paths:
        evidence_refs.append({"kind": "source_paths", "count": len(paths), "digest": _digest(paths)})
    if facts:
        evidence_refs.append({"kind": "support_facts", "count": len(facts), "digest": _digest([_fact_text(f) for f in facts])})
    provider_work_anchor = _work_order_anchor(work_order)
    provider_question = str(provider_work_anchor.get("anchor_text") or "")
    ptc_contracts = _worker_ptc_contracts(bundle)
    spec: dict[str, Any] = {
        "schema_version": "worker_result_spec.v1",
        "created_at": _now_iso(),
        "in_reply_to": mail_id,
        "work_order_id": work_order.get("work_order_id") or f"work-{mail_id}",
        "worker_role": worker_role,
        "result_status": status,
        "result_kind": result_kind,
        "input_spec_ref": {
            "schema_version": work_order.get("schema_version"),
            "payload_ref": work_order.get("payload_ref"),
            "acceptance_gate": work_order.get("acceptance_gate"),
        },
        "provider_question": provider_question,
        "provider_work_anchor": provider_work_anchor,
        "selected_capabilities": _selected_capabilities(bundle),
        "worker_ptc_contracts": ptc_contracts,
        "action_summary": _action_summary(worker_role=worker_role, result_kind=result_kind),
        "evidence_refs": evidence_refs,
        "storage_evidence": {
            "produced_count": int(produced_count),
            "node_count": len(nodes),
            "node_ids": nodes,
        }
        if worker_role == "memory_saver"
        else None,
        "support_bundle": bundle if worker_role == "memory_finder" else None,
        "worker_judgment": judgment,
        "retry_history": _retry_history(bundle),
        "typed_unavailable": typed_unavailable if result_kind == "typed_unavailable" else None,
        "postman_acceptance_status": postman_acceptance_status,
        "hard_nonclaims": [
            "postman_delivery_is_not_worker_success",
            "pane_text_is_not_result_sot",
            "worker_result_requires_provider_rejudgment_before_answer",
            "ptc_program_review_acceptance_is_not_execution_success",
            "changed_next_action_self_claim_is_not_enough",
        ],
    }
    spec["provider_rejudgment"] = build_provider_rejudgment(worker_result_spec=spec)
    validate_worker_result_spec(spec)
    return spec


def _digest(values: list[Any]) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _retry_history(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    retry = None
    if isinstance(bundle.get("ptc_retrieval_orchestrator"), Mapping):
        retry = bundle["ptc_retrieval_orchestrator"].get("retry_decision")
    if isinstance(bundle.get("candidate_reranker"), Mapping):
        retry = retry or bundle["candidate_reranker"].get("retry_decision")
    if isinstance(retry, Mapping):
        return [{"schema_version": "worker_retry_observation.v1", **dict(retry)}]
    return []


def _action_summary(*, worker_role: str, result_kind: str) -> str:
    if worker_role == "memory_saver":
        return "MS evaluated the save request and returned storage evidence or typed_unavailable."
    if result_kind == "support_bundle":
        return "MF evaluated the recall request and returned source-backed support for Provider rejudgment."
    return "MF could not return aligned source-backed support and returned typed_unavailable."


def validate_worker_result_spec(spec: Mapping[str, Any]) -> None:
    if spec.get("schema_version") != "worker_result_spec.v1":
        raise ValueError("invalid_worker_result_spec_schema")
    if spec.get("worker_role") not in {"memory_saver", "memory_finder"}:
        raise ValueError("invalid_worker_role")
    if spec.get("result_kind") not in {"storage_evidence", "support_bundle", "typed_unavailable"}:
        raise ValueError("invalid_result_kind")
    if not spec.get("work_order_id") or not spec.get("in_reply_to"):
        raise ValueError("missing_work_order_link")
    if not isinstance(spec.get("worker_judgment"), Mapping):
        raise ValueError("missing_worker_judgment")
    if not isinstance(spec.get("provider_rejudgment"), Mapping):
        raise ValueError("missing_provider_rejudgment")


__all__ = [
    "build_provider_rejudgment",
    "build_worker_result_spec",
    "validate_worker_result_spec",
]
