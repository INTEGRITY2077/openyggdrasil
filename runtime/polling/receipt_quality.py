from __future__ import annotations

from runtime.polling.ygg_poll_context import *  # noqa: F401,F403
from runtime.polling.mailbox_summary import *  # noqa: F401,F403

def _context_card_disabled_status() -> dict:
    if NATIVE_GOAL_MODE:
        return {"written": False, "status": "native_goal_mode"}
    if os.environ.get("OY_OP_CONTEXT_CARD", "1") == "0":
        return {"written": False, "status": "disabled"}
    return {}

def _short(value, limit: int = 220) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."

def _tst_supervisor_for_receipt(receipt: dict | None) -> dict:
    receipt = receipt or {}
    bundle, nested = _receipt_bundle(receipt)
    candidates = [
        receipt.get("tst_capability_supervisor"),
        receipt.get("tst_supervisor"),
        bundle.get("tst_capability_supervisor"),
        bundle.get("tst_supervisor"),
        nested.get("tst_capability_supervisor"),
        nested.get("tst_supervisor"),
    ]
    for container in (bundle, nested):
        ptc_worker_program = container.get("ptc_worker_program") if isinstance(container, dict) else None
        if isinstance(ptc_worker_program, dict):
            candidates.append(ptc_worker_program.get("tst_capability_supervisor"))
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}

def _capability_id_list(supervisor: dict, limit: int = 7) -> list[str]:
    allowlist = supervisor.get("tst_capability_allowlist")
    selected = allowlist.get("selected_capabilities") if isinstance(allowlist, dict) else None
    if not selected:
        selected = supervisor.get("selected_capabilities") or []
    ids: list[str] = []
    for item in selected:
        value = (
            item.get("tool_id") or item.get("capability_id") or item.get("id")
            if isinstance(item, dict)
            else item
        )
        if value:
            ids.append(str(value))
    return ids[:limit]

def _worker_program_public(supervisor: dict) -> dict:
    program = supervisor.get("worker_authored_ptc_program")
    if not isinstance(program, dict):
        program = {}
    review = supervisor.get("ptc_program_review")
    if not isinstance(review, dict):
        review = {}
    observation = supervisor.get("ptc_program_observation")
    if not isinstance(observation, dict):
        observation = {}
    delta = supervisor.get("observation_delta_gate")
    if not isinstance(delta, dict):
        delta = {}
    steps = [str(item) for item in (program.get("program_steps") or []) if str(item)]
    return {
        "goal": _short(program.get("self_defined_goal") or "role-scoped memory work", 180),
        "mode": str(program.get("program_mode") or "unknown"),
        "steps": " -> ".join(steps[:4]) + (f" -> ...(+{len(steps) - 4})" if len(steps) > 4 else ""),
        "review": str(review.get("review_status") or "missing"),
        "selected_tools": ", ".join(_capability_id_list(supervisor)) or "none",
        "observation_next": str(observation.get("next_action_candidate") or "unknown"),
        "delta_before": str(delta.get("next_action_before") or "before action"),
        "delta_after": str(delta.get("next_action_after") or observation.get("next_action_candidate") or "unknown"),
        "delta_verified": bool(delta.get("delta_verified")),
    }

def _worker_start_interpretation() -> dict:
    if MODE == "produce":
        return {
            "role_name": "Memory Saver",
            "read": "저장 후보인지 먼저 가르고, 출처/범위/중복/접목 가능성을 확인해야 합니다.",
            "work_plan": "source/range 확인 -> 기존 노드 비교 -> 저장 후보 정리 -> provenance/source/community 근거 확인",
            "action": "저장에 필요한 도구만 고르고, 그 순서대로 한 번 실행합니다.",
        }
    return {
        "role_name": "Memory Finder",
        "read": "질문의 고유 표식과 의도를 먼저 고정하고, 비슷한 기억을 대체 근거로 쓰지 않습니다.",
        "work_plan": "query anchor 확인 -> 후보 생성 -> source/provenance 확인 -> 정렬 안 맞으면 거절",
        "action": "회상에 필요한 읽기 도구만 고르고, 그 조합을 실행합니다.",
    }

def _receipt_public_summary(receipt: dict) -> dict:
    if not receipt:
        return {
            "result": "receipt_missing",
            "quality": "fail",
            "detail": "No receipt was found after operator_entrypoint finished.",
            "limitation": "No completed processing claim is allowed.",
        }
    if MODE == "produce":
        nodes = receipt.get("nodes") or []
        produced = receipt.get("produced_count", 0)
        return {
            "result": f"saved_nodes={len(nodes)} produced_count={produced}",
            "quality": "pass" if produced and nodes else "weak",
            "detail": f"receipt={receipt.get('receipt_id')} nodes={','.join(nodes[:4]) or 'none'}",
            "limitation": "This is storage receipt proof, not semantic truth or full topology proof.",
        }
    bundle = receipt.get("bundle") if isinstance(receipt.get("bundle"), dict) else {}
    nested = bundle.get("support_bundle") if isinstance(bundle.get("support_bundle"), dict) else {}
    facts = bundle.get("support_facts") or nested.get("support_facts") or []
    paths = bundle.get("source_paths") or nested.get("source_paths") or []
    ptc = bundle.get("ptc_retrieval_orchestrator") or nested.get("ptc_retrieval_orchestrator") or {}
    fact = facts[0] if facts else {}
    if isinstance(fact, dict):
        fact_text = " ".join(str(fact.get(key) or "") for key in ("subject", "predicate", "object")).strip()
    else:
        fact_text = str(fact or "")
    return {
        "result": f"support_facts={len(facts)} source_paths={len(paths)}",
        "quality": "pass_with_limit" if facts and paths else "weak",
        "detail": f"receipt={receipt.get('receipt_id')} ptc={ptc.get('coverage_state') if isinstance(ptc, dict) else 'none'} fact={_short(fact_text, 180)}",
        "limitation": "Use support facts only; this is not Graphify/ring/community full topology proof.",
    }

def _receipt_support_score(receipt: dict | None) -> int:
    facts, paths = _ptc_facts_paths(receipt)
    return len(facts) + len(paths)

def _receipt_quality(receipt: dict | None) -> str:
    return _receipt_public_summary(receipt or {}).get("quality", "fail")

def _mission_text(event: dict) -> str:
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    mission = payload.get("query_text") or payload.get("context_snapshot") or payload.get("decision") or ""
    return str(mission or "")

def _support_alignment_state(event: dict, receipt: dict | None) -> dict:
    mission = _mission_text(event).lower()
    bundle = receipt.get("bundle") if isinstance(receipt, dict) and isinstance(receipt.get("bundle"), dict) else {}
    worker_alignment = bundle.get("worker_query_alignment") if isinstance(bundle, dict) else None
    if isinstance(worker_alignment, dict):
        status = worker_alignment.get("status")
        if status == "misaligned":
            return {
                "status": "misaligned",
                "missing_markers": list(worker_alignment.get("missing_specific_tokens") or [])[:4],
                "reason": worker_alignment.get("reason_code") or "worker_query_alignment_misaligned",
            }
        if status in {"aligned", "aligned_with_limits"}:
            return {
                "status": "aligned_or_unchecked",
                "missing_markers": [],
                "reason": worker_alignment.get("reason_code") or "worker_query_alignment_aligned",
            }
    facts, paths = _ptc_facts_paths(receipt)
    haystack = " ".join(
        [
            json.dumps(facts, ensure_ascii=False).lower(),
            " ".join(str(path).lower() for path in paths),
            _receipt_public_summary(receipt or {}).get("detail", "").lower(),
        ]
    )
    markers = [
        marker
        for marker in re.findall(r"[a-z0-9][a-z0-9_-]{5,}", mission)
        if any(ch.isdigit() for ch in marker) or "_" in marker or len(marker) >= 24
        if marker not in {
            "claude",
            "hooks",
            "skills",
            "source",
            "support",
            "memory",
            "quality",
        }
    ]
    missing = [marker for marker in markers if marker not in haystack]
    if missing and facts:
        return {
            "status": "misaligned",
            "missing_markers": missing[:4],
            "reason": "high_specificity_query_marker_missing_from_support",
        }
    return {"status": "aligned_or_unchecked", "missing_markers": [], "reason": "no_blocking_marker_miss"}

def _receipt_public_summary_for_event(event: dict, receipt: dict | None) -> dict:
    summary = dict(_receipt_public_summary(receipt or {}))
    alignment = _support_alignment_state(event, receipt)
    summary["alignment_status"] = alignment["status"]
    summary["alignment_reason"] = alignment["reason"]
    summary["missing_markers"] = alignment["missing_markers"]
    if alignment["status"] == "misaligned":
        summary["quality"] = "weak"
        summary["limitation"] = (
            "Support exists but does not align with the high-specificity query marker; "
            "do not answer from this support."
        )
        summary["detail"] = (
            f"{summary.get('detail', '')} alignment=misaligned "
            f"missing_markers={','.join(alignment['missing_markers'])}"
        )
    return summary

def _receipt_quality_for_event(event: dict, receipt: dict | None) -> str:
    return _receipt_public_summary_for_event(event, receipt).get("quality", "fail")

def _first_support_fact_text(receipt: dict | None) -> str:
    bundle, nested = _receipt_bundle(receipt)
    facts = bundle.get("support_facts") or nested.get("support_facts") or []
    return _first_fact_text(facts if isinstance(facts, list) else [])

def _ralph_contract(event: dict) -> dict:
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    mission = (
        payload.get("context_snapshot")
        or payload.get("query_text")
        or payload.get("decision")
        or payload.get("source_ref")
        or payload
    )
    if MODE == "produce":
        return {
            "mission": mission,
            "role": "Memory Saver",
            "job": "decide whether this belongs in long-term memory, then store only if evidence and structure are sufficient",
            "self_question": "What exactly is worth preserving, and what would make this memory misleading later?",
            "action": "prepare and run one bounded save attempt",
            "evidence": "a saved node with provenance and a receipt, or a clear unavailable reason",
        }
    return {
        "mission": mission,
        "role": "Memory Finder",
        "job": "recover the relevant past memory, compare it with the current question, and return only supportable answer material",
        "self_question": "What is the user really trying to disambiguate, and which past memory would improve that answer?",
        "action": "choose retrieval tools, run one bounded find attempt, then judge whether the recovered memory is enough",
        "evidence": "support facts with source backing, or a clear unavailable reason",
    }

def _receipt_outcome(receipt: dict | None) -> dict:
    summary = _receipt_public_summary(receipt or {})
    quality = summary.get("quality")
    ok = quality in {"pass", "pass_with_limit"}
    if not receipt:
        return {
            "status": "no_evidence_yet",
            "enough": False,
            "observation": "아직 확인된 결과가 없습니다.",
            "next_choice": "다시 시도하거나 blocked로 닫을지 판단해야 합니다.",
        }
    if ok:
        fact = _first_support_fact_text(receipt)
        return {
            "status": "enough_with_limits",
            "enough": True,
            "observation": (
                "답변에 쓸 수 있는 근거가 확인됐습니다. "
                f"핵심 기억은 '{_short(fact, 180)}'입니다."
            ),
            "next_choice": "이 근거만 사용해서 답을 좁게 닫습니다.",
        }
    return {
        "status": "weak_or_unavailable",
        "enough": False,
        "observation": "결과는 나왔지만 답변 근거로 쓰기에는 부족합니다.",
        "next_choice": "부족한 이유를 밝히고 typed_unavailable 또는 blocked로 닫습니다.",
    }

def _answer_material(event: dict, receipt: dict | None) -> str:
    contract = _ralph_contract(event)
    fact = _first_support_fact_text(receipt)
    mission = str(contract.get("mission") or "")
    lowered = mission.lower()
    if not receipt:
        return "아직 답변에 쓸 근거가 확인되지 않았습니다. 근거 없이 안다고 말하지 않습니다."
    if "hook" in lowered and "skill" in lowered:
        return (
            "Hook은 특정 이벤트가 발생했을 때 자동으로 반드시 실행되어야 하는 동작에 씁니다. "
            "예를 들어 저장 직후 검사, 세션 종료 전 정리, 특정 이벤트가 올 때마다 반복되어야 하는 안전장치가 여기에 가깝습니다. "
            "Skill은 모델이 필요할 때 읽고 따라야 하는 작업 지침에 씁니다. "
            "예를 들어 문제를 어떻게 판단할지, 어떤 순서로 조사할지, 어떤 기준으로 답변을 구성할지처럼 상황에 맞춰 적용되는 절차가 여기에 가깝습니다. "
            "둘이 겹치면 자동 트리거와 강제 실행은 Hook에 두고, 의미 판단과 작업 방식은 Skill에 둡니다. "
            "이 답은 확인된 기억 범위에 한정합니다."
        )
    if fact and fact != "none":
        return (
            "회수한 기억의 핵심만 쓰면 이렇게 답할 수 있습니다: "
            f"{_short(fact, 260)} "
            "이 범위를 넘는 해석은 추가 근거가 필요합니다."
        )
    return "회수된 기억은 있지만 사용자 답변으로 바로 쓸 핵심 문장이 부족합니다. 부족하다고 답해야 합니다."

def _goal_contract(event: dict) -> dict:
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    if MODE == "produce":
        received = payload.get("context_snapshot") or payload.get("decision") or payload.get("source_ref") or payload
        return {
            "received": received,
            "objective": "요청을 장기 기억 후보로 해석하고, 저장 실행과 receipt 평가까지 닫는다.",
            "role_question": "이 내용은 나중에 다시 쓸 수 있는 기억으로 저장할 가치가 있는가?",
            "plan": "1 요청 해석 -> 2 저장 후보 판단 -> 3 MS1 produce 실행 -> 4 receipt 확인 -> 5 제한과 다음 행동 고정",
            "acceptance": "receipt_id가 있고 produced_count>0이며 생성 node가 확인되면 목표 달성",
            "fallback": "receipt가 없으면 최대 2회 재시도 후 blocked로 닫는다",
        }
    received = payload.get("query_text") or payload
    return {
        "received": received,
        "objective": "질문 의도를 해석하고, 기존 기억에서 근거를 찾아 Provider 답변 보강 가능 상태로 닫는다.",
        "role_question": "이 질문은 과거 기억에서 근거를 찾아 답변 해상도를 높여야 하는가?",
        "plan": "1 질문 의도 해석 -> 2 MF1 consume/PTC 검색 -> 3 support facts/source paths 평가 -> 4 부족하면 재시도 판단 -> 5 Provider 전달 제한 고정",
        "acceptance": "support_facts와 source_paths가 있거나 typed_unavailable 사유가 명확하면 목표를 닫는다",
        "fallback": "receipt가 없으면 최대 2회 재시도 후 blocked로 닫는다",
    }

def _receipt_bundle(receipt: dict | None) -> tuple[dict, dict]:
    receipt = receipt or {}
    bundle = receipt.get("bundle") if isinstance(receipt.get("bundle"), dict) else {}
    nested = bundle.get("support_bundle") if isinstance(bundle.get("support_bundle"), dict) else {}
    return bundle, nested

def _ptc_worker_program(receipt: dict | None) -> dict:
    bundle, nested = _receipt_bundle(receipt)
    program = bundle.get("ptc_worker_program") or nested.get("ptc_worker_program") or {}
    return program if isinstance(program, dict) else {}

def _ptc_facts_paths(receipt: dict | None) -> tuple[list, list]:
    bundle, nested = _receipt_bundle(receipt)
    facts = bundle.get("support_facts") or nested.get("support_facts") or []
    paths = bundle.get("source_paths") or nested.get("source_paths") or []
    return facts if isinstance(facts, list) else [], paths if isinstance(paths, list) else []

def _first_fact_text(facts: list) -> str:
    if not facts:
        return "none"
    fact = facts[0]
    if isinstance(fact, dict):
        for key in ("support_fact", "fact", "claim", "text", "summary"):
            if fact.get(key):
                return _short(fact.get(key), 220)
        spo = " ".join(str(fact.get(key) or "") for key in ("subject", "predicate", "object")).strip()
        return _short(spo or json.dumps(fact, ensure_ascii=False), 220)
    return _short(fact, 220)

def _ralph_todo_state(event: dict, receipt: dict | None, attempts: list[dict] | None = None) -> list[dict]:
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    mission = payload.get("query_text") or payload.get("context_snapshot") or payload.get("decision") or payload
    attempts = attempts or []
    bundle, nested = _receipt_bundle(receipt)
    program = _ptc_worker_program(receipt)
    orchestrator = bundle.get("ptc_retrieval_orchestrator") or nested.get("ptc_retrieval_orchestrator") or {}
    orchestrator = orchestrator if isinstance(orchestrator, dict) else {}
    discovery = program.get("tool_discovery") if isinstance(program.get("tool_discovery"), dict) else {}
    bounded = program.get("bounded_program") if isinstance(program.get("bounded_program"), dict) else {}
    calls = bounded.get("capability_calls") if isinstance(bounded.get("capability_calls"), list) else []
    call_ids = [
        str(call.get("capability_id"))
        for call in calls
        if isinstance(call, dict) and call.get("capability_id")
    ]
    selected_tools = discovery.get("selected_tool_ids") or call_ids
    facts, paths = _ptc_facts_paths(receipt)
    retry = program.get("retry_decision") if isinstance(program.get("retry_decision"), dict) else {}
    if not retry:
        retry = orchestrator.get("retry_decision") if isinstance(orchestrator.get("retry_decision"), dict) else {}
    coverage = program.get("coverage_state") or orchestrator.get("coverage_state") or "unknown"
    execution = bounded.get("execution_status") or program.get("execution_status") or "unknown"
    attempt_text = ",".join(
        f"{a.get('attempt')}:{a.get('returncode')}/{'receipt' if a.get('receipt_id') else 'no_receipt'}"
        for a in attempts
    ) or "none"
    first_fact = _first_fact_text(facts)
    support_quality = "pass" if facts and paths else "weak"
    execution_quality = "pass" if execution in {"completed", "ok"} or calls else "weak"
    plan_quality = "pass" if selected_tools else "weak"
    retry_status = retry.get("status") or "unknown"
    return [
        {
            "todo_id": "user_intent",
            "purpose": "현재 질문이 무엇을 구분하려는지 고정한다",
            "input": _short(mission, 220),
            "observed_result": "질문은 추상 정의가 아니라 실제 작업 배치와 반례를 요구한다",
            "quality": "pass",
            "next_action": "PTC 검색 계획으로 넘어간다",
        },
        {
            "todo_id": "ptc_plan",
            "purpose": "PTC가 어떤 읽기 도구를 조합할지 정한다",
            "input": f"attempts={attempt_text}",
            "observed_result": f"selected_tools={','.join(selected_tools) or 'none'}",
            "quality": plan_quality,
            "next_action": "선택된 읽기 도구 실행 결과를 확인한다",
        },
        {
            "todo_id": "ptc_execute",
            "purpose": "선택한 도구 프로그램이 실제로 실행됐는지 확인한다",
            "input": f"program_kind={bounded.get('program_kind') or 'unknown'}",
            "observed_result": f"execution={execution} tool_calls={len(calls)}",
            "quality": execution_quality,
            "next_action": "실행 결과가 답변 근거로 충분한지 평가한다",
        },
        {
            "todo_id": "support_eval",
            "purpose": "support facts/source paths가 답변 근거로 충분한지 평가한다",
            "input": f"coverage={coverage}",
            "observed_result": f"support_facts={len(facts)} source_paths={len(paths)} first_fact={first_fact}",
            "quality": support_quality,
            "next_action": "weak면 재검색을 판단하고, pass면 답변 재료로 승격한다",
        },
        {
            "todo_id": "retry_eval",
            "purpose": "검색 결과가 약할 때 재검색이 필요한지 판단한다",
            "input": f"retry={retry_status}",
            "observed_result": f"reason={retry.get('reason') or 'none'} max_attempts={retry.get('max_attempts') or 'unknown'}",
            "quality": "pass" if support_quality == "pass" and retry_status in {"not_required", "unknown"} else "weak",
            "next_action": "현재 근거만으로 답을 낼지, 부족하다고 닫을지 정한다",
        },
        {
            "todo_id": "answer_plan",
            "purpose": "PTC 결과를 사용자 답변 구조로 변환한다",
            "input": first_fact,
            "observed_result": (
                "저장 직후 자동 검사는 Hook 후보, 답변 품질 판단은 Skill 후보, "
                "겹치면 자동 실행과 판단 기준을 분리한다"
            ),
            "quality": support_quality,
            "next_action": "초안, 검토, 보강, 최종 답변으로 진행한다",
        },
    ]


__all__ = [
    "_context_card_disabled_status",
    "_short",
    "_tst_supervisor_for_receipt",
    "_capability_id_list",
    "_worker_program_public",
    "_worker_start_interpretation",
    "_receipt_public_summary",
    "_receipt_support_score",
    "_receipt_quality",
    "_mission_text",
    "_support_alignment_state",
    "_receipt_public_summary_for_event",
    "_receipt_quality_for_event",
    "_first_support_fact_text",
    "_ralph_contract",
    "_receipt_outcome",
    "_answer_material",
    "_goal_contract",
    "_receipt_bundle",
    "_ptc_worker_program",
    "_ptc_facts_paths",
    "_first_fact_text",
    "_ralph_todo_state",
]
