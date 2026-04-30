from __future__ import annotations

import json
import re
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z0-9\uAC00-\uD7A3\u0600-\u06FF]+", re.UNICODE)
MIN_TOKEN_LEN = 2
MAX_FACTS = 12
FORBIDDEN_ROUTING_TEXT = (
    "---\nname:",
    ".skill.md",
    "<instructions>",
    "file://",
    "d:/",
    "d:\\",
    "c:/",
    "c:\\",
    '"skill_body_included": true',
    '"raw_provider_material_included": true',
    '"portable_local_path_included": true',
)


def _unique_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for match in TOKEN_RE.findall(text or ""):
        token = match.casefold()
        if len(token) < MIN_TOKEN_LEN:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _collect_topics(packets: list[dict[str, Any]]) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for packet in packets:
        topic = str(packet.get("scope", {}).get("topic") or "").strip()
        if not topic:
            continue
        folded = topic.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        topics.append(topic)
    return topics


def _collect_support_facts(packets: list[dict[str, Any]]) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for packet in packets:
        payload = packet.get("payload", {})
        for fact in payload.get("facts", []):
            fact_text = str(fact).strip()
            folded = fact_text.casefold()
            if len(fact_text) < 4:
                continue
            if folded in seen:
                continue
            seen.add(folded)
            facts.append(fact_text)
    return facts[:MAX_FACTS]


def json_like(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)


def _collect_routing_receipts(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for packet in packets:
        payload = packet.get("payload", {})
        if not isinstance(payload, dict):
            continue
        for receipt in payload.get("routing_receipts") or []:
            if isinstance(receipt, dict):
                receipts.append(dict(receipt))
    return receipts


def _state_routing_receipts(answer_payload: dict[str, Any]) -> list[dict[str, Any]]:
    state = answer_payload.get("state")
    if not isinstance(state, dict):
        return []
    receipts = state.get("routing_receipts")
    if not isinstance(receipts, list):
        return []
    return [dict(receipt) for receipt in receipts if isinstance(receipt, dict)]


def _routing_receipt_has_unsafe_flags(receipt: dict[str, Any]) -> bool:
    return any(
        receipt.get(key) is True
        for key in (
            "skill_body_included",
            "raw_provider_material_included",
            "portable_local_path_included",
            "advisory_metadata_lowered_effort",
            "live_readiness_claimed",
            "production_readiness_claimed",
            "reasoning_lease_solved_claimed",
            "target_readiness_claimed",
        )
    )


def _contains_forbidden_routing_text(value: Any) -> bool:
    rendered = json_like(value).casefold().replace("\\", "/")
    return any(token.casefold().replace("\\", "/") in rendered for token in FORBIDDEN_ROUTING_TEXT)


def _routing_receipt_use_state(
    *,
    packets: list[dict[str, Any]],
    answer_payload: dict[str, Any],
) -> dict[str, Any]:
    packet_receipts = _collect_routing_receipts(packets)
    state_receipts = _state_routing_receipts(answer_payload)
    answer_text = str(answer_payload.get("answer_text") or "")
    state_text = json_like(state_receipts)
    haystack = f"{answer_text}\n{state_text}".casefold()
    expected_tokens: list[str] = []
    evidence_ids: list[str] = []
    for receipt in packet_receipts:
        for key in (
            "route_id",
            "receipt_id",
            "approved_effort",
            "lease_group",
            "provider_route_summary",
        ):
            value = str(receipt.get(key) or "").strip()
            if value:
                expected_tokens.append(value)
        for evidence_ref in receipt.get("evidence_refs") or []:
            if isinstance(evidence_ref, dict) and evidence_ref.get("evidence_id"):
                evidence_id = str(evidence_ref["evidence_id"])
                evidence_ids.append(evidence_id)
                expected_tokens.append(evidence_id)
    token_hits = [
        token
        for token in expected_tokens
        if token.casefold() in haystack
    ]
    unsafe = (
        any(_routing_receipt_has_unsafe_flags(receipt) for receipt in packet_receipts)
        or any(_routing_receipt_has_unsafe_flags(receipt) for receipt in state_receipts)
        or _contains_forbidden_routing_text(answer_text)
        or _contains_forbidden_routing_text(state_receipts)
    )
    used = bool(packet_receipts) and bool(state_receipts) and bool(token_hits)
    return {
        "routing_receipt_count": len(packet_receipts),
        "routing_receipt_state_count": len(state_receipts),
        "routing_receipt_used": used,
        "routing_receipt_unsafe_use": unsafe,
        "routing_receipt_token_hit_count": len(token_hits),
        "routing_receipt_route_ids": [
            str(receipt.get("route_id"))
            for receipt in packet_receipts
            if receipt.get("route_id")
        ],
        "routing_receipt_evidence_ids": evidence_ids[:16],
        "routing_receipt_quality_decision": (
            "red_captured"
            if unsafe or (packet_receipts and not used)
            else "green_passed"
            if packet_receipts and used
            else "not_applicable"
        ),
    }


def _match_count(candidates: list[str], haystack: str) -> int:
    haystack_folded = haystack.casefold()
    matched = 0
    for item in candidates:
        folded = item.casefold()
        if folded and folded in haystack_folded:
            matched += 1
    return matched


def _grade_from_score(score: float) -> str:
    if score >= 0.85:
        return "A"
    if score >= 0.70:
        return "B"
    if score >= 0.55:
        return "C"
    return "D"


def quality_gate_decision(verdict: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not verdict.get("question_answered", False):
        reasons.append("question_not_clearly_answered")
    if verdict.get("unsupported_claim_risk") in {"medium", "high"}:
        reasons.append(f"unsupported_claim_risk:{verdict.get('unsupported_claim_risk')}")
    if verdict.get("support_sufficient") and not verdict.get("support_used"):
        reasons.append("support_not_used")
    if verdict.get("quality_grade") in {"C", "D"}:
        reasons.append(f"quality_grade:{verdict.get('quality_grade')}")
    if verdict.get("routing_receipt_quality_decision") == "red_captured":
        reasons.append("routing_receipt_red_captured")
    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }


def evaluate_answer_quality(
    *,
    query_text: str,
    packets: list[dict[str, Any]],
    answer_payload: dict[str, Any],
    decision_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    answer_text = str(answer_payload.get("answer_text") or "").strip()
    rendering_mode = str(answer_payload.get("rendering_mode") or "")
    packet_count = len(packets)

    question_tokens = _unique_tokens(query_text)
    answer_tokens = set(_unique_tokens(answer_text))
    question_token_hit_count = sum(1 for token in question_tokens if token in answer_tokens)
    question_coverage = (
        question_token_hit_count / max(len(question_tokens), 1)
        if question_tokens
        else 0.0
    )

    support_facts = _collect_support_facts(packets)
    support_fact_match_count = _match_count(support_facts, answer_text)
    topics = _collect_topics(packets)
    topic_match_count = _match_count(topics, answer_text)
    routing_receipt_state = _routing_receipt_use_state(
        packets=packets,
        answer_payload=answer_payload,
    )

    support_sufficient = packet_count > 0
    used_support = (
        support_fact_match_count > 0
        or topic_match_count > 0
        or routing_receipt_state["routing_receipt_used"]
    )
    fallback_used = rendering_mode in {
        "deterministic-fallback",
        "deterministic-assurance-fallback",
    }

    if routing_receipt_state["routing_receipt_unsafe_use"]:
        unsupported_claim_risk = "high"
    elif not support_sufficient:
        unsupported_claim_risk = "high"
    elif not used_support:
        unsupported_claim_risk = "medium"
    else:
        unsupported_claim_risk = "low"

    question_answered = bool(answer_text) and (
        question_coverage >= 0.20
        or support_fact_match_count > 0
        or topic_match_count > 0
        or routing_receipt_state["routing_receipt_used"]
        or rendering_mode in {"hermes-answer-edge", "hermes-assured-answer-edge"}
    )

    score = 0.0
    score += min(question_coverage, 1.0) * 0.45
    if support_sufficient:
        score += 0.20
    if used_support:
        score += 0.20
    if (
        routing_receipt_state["routing_receipt_used"]
        and not routing_receipt_state["routing_receipt_unsafe_use"]
    ):
        score += 0.25
    if not fallback_used:
        score += 0.10
    if unsupported_claim_risk == "medium":
        score -= 0.10
    elif unsupported_claim_risk == "high":
        score -= 0.20
    score = max(0.0, min(1.0, score))

    notes: list[str] = []
    if not support_sufficient:
        notes.append("no_packet_support")
    if support_sufficient and not used_support:
        notes.append("support_selected_but_not_reflected")
    if (
        routing_receipt_state["routing_receipt_count"]
        and not routing_receipt_state["routing_receipt_used"]
    ):
        notes.append("routing_receipt_not_reflected")
    if routing_receipt_state["routing_receipt_unsafe_use"]:
        notes.append("routing_receipt_unsafe_use")
    if fallback_used:
        notes.append("fallback_answer_rendering")
    if not question_answered:
        notes.append("question_not_clearly_answered")

    missed_required_points: list[str] = []
    if support_sufficient and not used_support and topics:
        missed_required_points.extend(topics[:3])

    fallback_order = (
        decision_report.get("state", {}).get("fallback", {}).get("order", [])
        if isinstance(decision_report, dict)
        else []
    )

    verdict = {
        "evaluation_mode": "deterministic-answer-quality-v1",
        "question_answered": question_answered,
        "support_sufficient": support_sufficient,
        "support_used": used_support,
        "fallback_used": fallback_used,
        "fallback_order": fallback_order,
        "question_token_count": len(question_tokens),
        "question_token_hit_count": question_token_hit_count,
        "question_coverage": round(question_coverage, 4),
        "packet_count": packet_count,
        "packet_types": sorted({str(packet.get("message_type")) for packet in packets}),
        "support_fact_count": len(support_facts),
        "support_fact_match_count": support_fact_match_count,
        "topic_count": len(topics),
        "topic_match_count": topic_match_count,
        "unsupported_claim_risk": unsupported_claim_risk,
        "unsupported_claim_count": 1 if unsupported_claim_risk == "high" else 0,
        "missed_required_points": missed_required_points,
        "quality_score": round(score, 4),
        "quality_grade": _grade_from_score(score),
        "notes": notes,
        "answer_length": len(answer_text),
        "answer_hash": answer_payload.get("answer_hash"),
        "rendering_mode": rendering_mode,
        **routing_receipt_state,
    }
    gate = quality_gate_decision(verdict)
    verdict["quality_gate_passed"] = gate["passed"]
    verdict["quality_gate_reasons"] = gate["reasons"]
    return verdict
