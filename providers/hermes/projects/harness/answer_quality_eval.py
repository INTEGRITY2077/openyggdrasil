from __future__ import annotations

import re
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z0-9\uAC00-\uD7A3\u0600-\u06FF]+", re.UNICODE)
MIN_TOKEN_LEN = 2
MAX_FACTS = 12


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

    support_sufficient = packet_count > 0
    used_support = support_fact_match_count > 0 or topic_match_count > 0
    fallback_used = rendering_mode in {
        "deterministic-fallback",
        "deterministic-assurance-fallback",
    }

    if not support_sufficient:
        unsupported_claim_risk = "high"
    elif not used_support:
        unsupported_claim_risk = "medium"
    else:
        unsupported_claim_risk = "low"

    question_answered = bool(answer_text) and (
        question_coverage >= 0.20
        or support_fact_match_count > 0
        or topic_match_count > 0
        or rendering_mode in {"hermes-answer-edge", "hermes-assured-answer-edge"}
    )

    score = 0.0
    score += min(question_coverage, 1.0) * 0.45
    if support_sufficient:
        score += 0.20
    if used_support:
        score += 0.20
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
    }
    gate = quality_gate_decision(verdict)
    verdict["quality_gate_passed"] = gate["passed"]
    verdict["quality_gate_reasons"] = gate["reasons"]
    return verdict
