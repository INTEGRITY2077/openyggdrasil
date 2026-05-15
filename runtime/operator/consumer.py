"""
Memory Finder consumer runtime.

The primary recall route is the deterministic read-only PTC retrieval
orchestrator. Legacy BM25/lifecycle/edge search remains only as a degraded
fallback when the orchestrator is unavailable.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime.log_event import log_event
from runtime.ptc.primitives import (
    search_vault_bm25,
    format_consumer_result,
    load_vault,
    load_edges,
    _boost_by_edges,
)

from .helpers import deliver_receipt, write_operator_receipt


_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}|[\uac00-\ud7a3]{2,}")
_GENERIC_QUERY_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "based",
    "between",
    "can",
    "case",
    "code",
    "docs",
    "does",
    "enough",
    "for",
    "from",
    "get",
    "give",
    "how",
    "into",
    "just",
    "later",
    "like",
    "line",
    "make",
    "model",
    "more",
    "not",
    "one",
    "only",
    "same",
    "should",
    "that",
    "the",
    "then",
    "this",
    "use",
    "used",
    "uses",
    "what",
    "when",
    "where",
    "which",
    "with",
    "기준",
    "나중에",
    "대충",
    "문서",
    "보면",
    "어떤",
    "언제",
    "위키",
    "정도",
    "질문",
    "하면",
}
_BOUNDARY_CUE_TERMS = {
    "boundary",
    "category",
    "criteria",
    "criterion",
    "different",
    "difference",
    "distinction",
    "enough",
    "fourth",
    "kind",
    "layer",
    "runtime",
    "same",
    "sufficient",
    "type",
    "versus",
    "when",
    "가르",
    "나눠",
    "다른",
    "묶어",
    "선",
    "언제",
    "올리",
    "끝내",
    "차이",
    "층위",
    "충분",
    "같은",
    "과한",
    "구분",
}

try:
    from runtime.retrieval.pathfinder_tools import build_ring_support_bundle
except ImportError as exc:
    log_event("optional_import_unavailable", module="runtime.retrieval.pathfinder_tools", reason=str(exc))
    build_ring_support_bundle = None

try:
    from runtime.retrieval.ptc_retrieval_orchestrator import build_ptc_retrieval_orchestrator_result
except ImportError as exc:
    log_event(
        "optional_import_unavailable",
        module="runtime.retrieval.ptc_retrieval_orchestrator",
        reason=str(exc),
    )
    build_ptc_retrieval_orchestrator_result = None

try:
    from runtime.ptc.tool_search_supervisor import build_memory_finder_tst_result
except ImportError as exc:
    log_event("optional_import_unavailable", module="runtime.ptc.tool_search_supervisor", reason=str(exc))
    build_memory_finder_tst_result = None

try:
    from runtime.ptc.engine import build_query_adaptive_pathfinder_plan
    from runtime.retrieval.programmatic_tool_runtime import (
        build_pathfinder_bundle_via_programmatic_tool_runtime,
    )
except ImportError as exc:
    log_event("optional_import_unavailable", module="runtime.ptc.engine_pathfinder", reason=str(exc))
    build_query_adaptive_pathfinder_plan = None
    build_pathfinder_bundle_via_programmatic_tool_runtime = None

# PTC advisory import (lazy)
try:
    from runtime.ptc.sandbox_executor import execute_ptc_code as _ptc_exec
except ImportError as exc:
    log_event("optional_import_unavailable", module="runtime.ptc.sandbox_executor", reason=str(exc))
    _ptc_exec = None


def _support_facts_and_paths(bundle: dict) -> tuple[list, list]:
    nested = bundle.get("support_bundle") if isinstance(bundle.get("support_bundle"), dict) else {}
    facts = bundle.get("support_facts") or nested.get("support_facts") or []
    paths = bundle.get("source_paths") or nested.get("source_paths") or []
    return list(facts or []), list(paths or [])


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _WORD_RE.finditer(text or "")}


def _normalize_query_term(token: str) -> str:
    normalized = token.lower().replace("_", "-").strip("-")
    if normalized.isascii() and len(normalized) > 4 and normalized.endswith("s") and not normalized.endswith("ss"):
        normalized = normalized[:-1]
    return normalized


def _normalized_tokens(text: str) -> set[str]:
    return {term for token in _tokens(text) if (term := _normalize_query_term(token))}


def _significant_query_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in _tokens(text):
        normalized = _normalize_query_term(token)
        if not normalized or normalized in _GENERIC_QUERY_STOPWORDS:
            continue
        if len(normalized) < 3 and normalized.isascii():
            continue
        terms.add(normalized)
    return terms


def _is_boundary_question(text: str, query_tokens: set[str]) -> bool:
    lowered = f" {str(text or '').lower()} "
    has_phrase_cue = any(phrase in lowered for phrase in (" vs ", " versus ", " or ", "랑", "하고", "와 ", "과 "))
    has_text_cue = any(cue in lowered for cue in _BOUNDARY_CUE_TERMS)
    has_token_cue = bool(query_tokens & _BOUNDARY_CUE_TERMS)
    return has_phrase_cue or has_text_cue or has_token_cue


def _generic_boundary_alignment(*, query_text: str, support_tokens: set[str]) -> dict:
    query_tokens = _tokens(query_text)
    significant_terms = _significant_query_terms(query_text)
    if not _is_boundary_question(query_text, query_tokens) or len(significant_terms) < 2:
        return {
            "applies": False,
            "covered_terms": [],
            "missing_terms": [],
            "required_terms": [],
        }
    ascii_terms = {term for term in significant_terms if term.isascii()}
    required_terms = ascii_terms if len(ascii_terms) >= 2 else significant_terms
    covered = sorted(term for term in required_terms if term in support_tokens)
    missing = sorted(term for term in required_terms if term not in support_tokens)
    return {
        "applies": True,
        "covered_terms": covered[:20],
        "missing_terms": missing[:20],
        "required_terms": sorted(required_terms)[:20],
    }


def _high_specificity_tokens(text: str) -> set[str]:
    terms: set[str] = set()
    for token in _tokens(text):
        normalized = _normalize_query_term(token)
        if any(ch.isdigit() for ch in token) or "_" in token or "-" in token or len(normalized) >= 24:
            terms.add(normalized)
    return terms


def _support_text(value) -> str:
    if isinstance(value, dict):
        parts = []
        for key in [
            "subject",
            "predicate",
            "object",
            "summary",
            "text",
            "source_ref",
            "source_path",
            "topic_key",
            "topic_id",
            "community_id",
            "origin_locator",
        ]:
            if value.get(key):
                parts.append(str(value.get(key)))
        for key in ["support_facts", "source_paths", "selected", "candidate_reranker"]:
            if key in value:
                parts.append(_support_text(value.get(key)))
        return "\n".join(part for part in parts if part)
    if isinstance(value, list):
        return "\n".join(_support_text(item) for item in value)
    return str(value or "")


def _memory_finder_alignment(*, query_text: str, bundle: dict) -> dict:
    facts, paths = _support_facts_and_paths(bundle if isinstance(bundle, dict) else {})
    support_text = "\n".join(
        [
            _support_text(facts),
            _support_text(paths),
            _support_text((bundle or {}).get("candidate_reranker") if isinstance(bundle, dict) else {}),
            _support_text((bundle or {}).get("support_bundle") if isinstance(bundle, dict) else {}),
        ]
    )
    query_tokens = _tokens(query_text)
    support_tokens = _tokens(support_text)
    normalized_support_tokens = _normalized_tokens(support_text)
    high_specificity = _high_specificity_tokens(query_text)
    missing_specific = sorted(token for token in high_specificity if token not in normalized_support_tokens)
    overlap = sorted(query_tokens & support_tokens)
    overlap_score = 0.0 if not query_tokens else len(overlap) / max(len(query_tokens), 1)
    boundary_alignment = _generic_boundary_alignment(query_text=query_text, support_tokens=normalized_support_tokens)
    missing_boundary_markers: list[str] = []
    if boundary_alignment["applies"] and len(boundary_alignment["covered_terms"]) < 2:
        missing_boundary_markers.extend(
            f"query_term:{term}" for term in boundary_alignment["missing_terms"][:8]
        )
    if boundary_alignment["applies"] and missing_boundary_markers:
        status = "misaligned"
        reason = "paired_boundary_marker_missing_from_support"
    elif missing_specific:
        status = "misaligned"
        reason = "high_specificity_marker_missing_from_support"
    elif facts and paths and high_specificity:
        status = "aligned"
        reason = "high_specificity_marker_present_in_support"
    elif facts and paths:
        status = "aligned_with_limits"
        reason = "source_backed_support_present_without_specific_marker_gate"
    else:
        status = "insufficient_support"
        reason = "support_facts_or_source_paths_missing"
    return {
        "schema_version": "memory_finder_query_alignment.v1",
        "status": status,
        "reason_code": reason,
        "query_token_count": len(query_tokens),
        "support_token_count": len(support_tokens),
        "overlap_score": round(overlap_score, 4),
        "matched_specific_tokens": sorted(token for token in high_specificity if token in normalized_support_tokens)[:20],
        "missing_specific_tokens": missing_specific[:20],
        "missing_boundary_markers": missing_boundary_markers,
        "boundary_alignment": boundary_alignment,
        "hard_gate_applied": bool(high_specificity),
    }


def _misaligned_support_bundle(*, query_text: str, bundle: dict, alignment: dict) -> dict:
    original_facts, original_paths = _support_facts_and_paths(bundle if isinstance(bundle, dict) else {})
    typed_unavailable = {
        "schema_version": "typed_unavailable.v1",
        "reason_code": "typed_unavailable_misaligned_support",
        "query_hash": hashlib.sha256(str(query_text or "").encode("utf-8")).hexdigest()[:12],
        "missing_specific_tokens": alignment.get("missing_specific_tokens") or [],
        "observed_support_fact_count": len(original_facts),
        "observed_source_path_count": len(original_paths),
        "hard_nonclaims": [
            "support_count_is_not_alignment",
            "near_miss_support_is_not_answer_material",
            "provider_rejudgment_still_required",
        ],
    }
    guarded = dict(bundle if isinstance(bundle, dict) else {})
    guarded["original_support_summary"] = {
        "support_fact_count": len(original_facts),
        "source_path_count": len(original_paths),
        "withheld_reason": "misaligned_support",
    }
    guarded["support_facts"] = []
    guarded["source_paths"] = []
    guarded["typed_unavailable"] = typed_unavailable
    guarded["support_bundle"] = {
        "schema_version": "support_bundle.v1",
        "support_facts": [],
        "source_paths": [],
        "typed_unavailable": typed_unavailable,
    }
    guarded["worker_query_alignment"] = alignment
    return guarded


def _insufficient_support_bundle(*, query_text: str, bundle: dict, alignment: dict) -> dict:
    original_facts, original_paths = _support_facts_and_paths(bundle if isinstance(bundle, dict) else {})
    typed_unavailable = {
        "schema_version": "typed_unavailable.v1",
        "reason_code": "typed_unavailable_support_facts_or_source_paths_missing",
        "query_hash": hashlib.sha256(str(query_text or "").encode("utf-8")).hexdigest()[:12],
        "observed_support_fact_count": len(original_facts),
        "observed_source_path_count": len(original_paths),
        "hard_nonclaims": [
            "completed_status_requires_support_facts",
            "completed_status_requires_source_paths",
            "provider_rejudgment_still_required",
        ],
    }
    guarded = dict(bundle if isinstance(bundle, dict) else {})
    guarded["original_support_summary"] = {
        "support_fact_count": len(original_facts),
        "source_path_count": len(original_paths),
        "withheld_reason": "support_facts_or_source_paths_missing",
    }
    guarded["support_facts"] = []
    guarded["source_paths"] = []
    guarded["typed_unavailable"] = typed_unavailable
    guarded["support_bundle"] = {
        "schema_version": "support_bundle.v1",
        "support_facts": [],
        "source_paths": [],
        "typed_unavailable": typed_unavailable,
    }
    guarded["worker_query_alignment"] = alignment
    return guarded


def _safe_index_cursor(bundle: dict) -> dict:
    nested_bundle = bundle.get("support_bundle") if isinstance(bundle.get("support_bundle"), dict) else {}
    if isinstance(bundle.get("safe_index_cursor"), dict):
        return bundle["safe_index_cursor"]
    if isinstance(nested_bundle.get("safe_index_cursor"), dict):
        return nested_bundle["safe_index_cursor"]
    return {}


def _unsafe_cursor_bundle(*, query_text: str, bundle: dict, alignment: dict) -> dict:
    original_facts, original_paths = _support_facts_and_paths(bundle if isinstance(bundle, dict) else {})
    safe_index_cursor = _safe_index_cursor(bundle if isinstance(bundle, dict) else {})
    typed_unavailable = {
        "schema_version": "typed_unavailable.v1",
        "reason_code": "typed_unavailable_unsafe_index_cursor",
        "query_hash": hashlib.sha256(str(query_text or "").encode("utf-8")).hexdigest()[:12],
        "safe_index_cursor": safe_index_cursor,
        "observed_support_fact_count": len(original_facts),
        "observed_source_path_count": len(original_paths),
        "hard_nonclaims": [
            "safe_index_cursor_outside_is_not_final_support",
            "source_backed_candidate_is_not_safe_support",
            "provider_rejudgment_still_required",
        ],
    }
    guarded = dict(bundle if isinstance(bundle, dict) else {})
    guarded["original_support_summary"] = {
        "support_fact_count": len(original_facts),
        "source_path_count": len(original_paths),
        "withheld_reason": "unsafe_index_cursor",
    }
    guarded["support_facts"] = []
    guarded["source_paths"] = []
    guarded["safe_index_cursor"] = safe_index_cursor
    guarded["typed_unavailable"] = typed_unavailable
    guarded["support_bundle"] = {
        "schema_version": "support_bundle.v1",
        "support_facts": [],
        "source_paths": [],
        "typed_unavailable": typed_unavailable,
    }
    guarded["worker_query_alignment"] = alignment
    return guarded


def _support_snippet(text: str, covered_terms: set[str]) -> str:
    normalized_terms = {term.lower() for term in covered_terms}
    for raw_line in str(text or "").splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        line_terms = _normalized_tokens(line)
        if len(line_terms & normalized_terms) >= 2:
            return line[:500]
    return " ".join(str(text or "").split())[:500]


def _boundary_fallback_bundle(
    *,
    query_text: str,
    vault: Path,
    prior_bundle: dict,
    reason_code: str,
) -> dict | None:
    significant_terms = _significant_query_terms(query_text)
    if len(significant_terms) < 2:
        return None
    candidates: list[dict] = []
    for path in vault.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        doc_terms = _normalized_tokens(text)
        covered = sorted(significant_terms & doc_terms)
        if len(covered) < 2:
            continue
        relative = path.relative_to(vault).as_posix()
        candidates.append(
            {
                "path": relative,
                "covered_terms": covered[:20],
                "score": len(covered),
                "snippet": _support_snippet(text, set(covered)),
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-int(row["score"]), row["path"]))
    selected = candidates[:5]
    support_facts = [
        {
            "source_path": row["path"],
            "covered_terms": row["covered_terms"],
            "text": row["snippet"],
        }
        for row in selected
    ]
    source_paths = [row["path"] for row in selected]
    return {
        "schema_version": "boundary_fallback_support_bundle.v1",
        "query": query_text,
        "support_facts": support_facts,
        "source_paths": source_paths,
        "support_bundle": {
            "schema_version": "support_bundle.v1",
            "support_facts": support_facts,
            "source_paths": source_paths,
            "hard_nonclaims": [
                "boundary_fallback_candidate_still_requires_alignment_gate",
                "source_path_presence_is_not_final_answer",
                "provider_rejudgment_still_required",
            ],
        },
        "boundary_fallback": {
            "schema_version": "boundary_alignment_fallback.v1",
            "reason_code": reason_code,
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "selected_paths": source_paths,
            "prior_support_summary": {
                "support_fact_count": len(_support_facts_and_paths(prior_bundle)[0]),
                "source_path_count": len(_support_facts_and_paths(prior_bundle)[1]),
            },
        },
    }


def _prepare_memory_finder_bundle(*, query_text: str, bundle: dict, status: str) -> tuple[dict, str]:
    prepared = dict(bundle if isinstance(bundle, dict) else {})
    alignment = _memory_finder_alignment(query_text=query_text, bundle=prepared)
    prepared["worker_query_alignment"] = alignment
    if status == "completed" and alignment.get("status") == "misaligned":
        return _misaligned_support_bundle(query_text=query_text, bundle=prepared, alignment=alignment), (
            "typed_unavailable_misaligned_support"
        )
    if status == "completed" and alignment.get("status") == "insufficient_support":
        return _insufficient_support_bundle(query_text=query_text, bundle=prepared, alignment=alignment), (
            "typed_unavailable_support_facts_or_source_paths_missing"
        )
    if status == "completed" and _safe_index_cursor(prepared).get("status") == "outside":
        return _unsafe_cursor_bundle(query_text=query_text, bundle=prepared, alignment=alignment), (
            "typed_unavailable_unsafe_index_cursor"
        )
    return prepared, status


def _prepare_memory_finder_bundle_with_fallback(
    *,
    query_text: str,
    bundle: dict,
    status: str,
    vault: Path,
) -> tuple[dict, str]:
    prepared, receipt_status = _prepare_memory_finder_bundle(
        query_text=query_text,
        bundle=bundle,
        status=status,
    )
    if receipt_status not in {
        "typed_unavailable_misaligned_support",
        "typed_unavailable_support_facts_or_source_paths_missing",
    }:
        return prepared, receipt_status
    fallback = _boundary_fallback_bundle(
        query_text=query_text,
        vault=vault,
        prior_bundle=prepared,
        reason_code=receipt_status,
    )
    if fallback is None:
        return prepared, receipt_status
    fallback["initial_worker_query_alignment"] = prepared.get("worker_query_alignment")
    return _prepare_memory_finder_bundle(
        query_text=query_text,
        bundle=fallback,
        status="completed",
    )


def _memory_finder_judgment(*, query_text: str, bundle: dict, status: str) -> dict:
    """Provider-safe worker judgment summary for MF receipts."""
    facts, paths = _support_facts_and_paths(bundle if isinstance(bundle, dict) else {})
    alignment = (
        bundle.get("worker_query_alignment")
        if isinstance(bundle, dict) and isinstance(bundle.get("worker_query_alignment"), dict)
        else _memory_finder_alignment(query_text=query_text, bundle=bundle if isinstance(bundle, dict) else {})
    )
    success = (
        status == "completed"
        and bool(facts)
        and bool(paths)
        and alignment.get("status") in {"aligned", "aligned_with_limits"}
    )
    safe_index_cursor = _safe_index_cursor(bundle if isinstance(bundle, dict) else {})
    if safe_index_cursor.get("status") == "outside":
        success = False
    return {
        "schema_version": "worker_judgment.v1",
        "worker_role": "memory_finder",
        "small_goal": "decide whether the Find Request has aligned source-backed support",
        "todo": [
            "identify the recall target",
            "run the role-scoped bounded recall path",
            "inspect support facts and source refs",
            "close as support_bundle or typed_unavailable",
        ],
        "success_evidence": [
            "support_facts are present",
            "source refs or source paths are present",
            "Result Receipt was written",
        ],
        "failure_conditions": [
            "no aligned support",
            "source refs are missing",
            "candidate is stale or misaligned",
            "similarity match exists without evidence",
        ],
        "observation": {
            "query_hash": hashlib.sha256(str(query_text or "").encode("utf-8")).hexdigest()[:12],
            "status": status,
            "support_fact_count": len(facts),
            "source_path_count": len(paths),
            "alignment_status": alignment.get("status"),
            "alignment_reason": alignment.get("reason_code"),
            "safe_index_cursor_status": safe_index_cursor.get("status"),
            "safe_index_cursor_allowed": safe_index_cursor.get("final_support_allowed"),
        },
        "judgment": "success" if success else "typed_unavailable",
        "close_decision": "support_bundle"
        if success
        else "typed_unavailable_unsafe_index_cursor"
        if safe_index_cursor.get("status") == "outside"
        else alignment.get("reason_code", "typed_unavailable_no_support"),
        "hard_nonclaims": [
            "candidate_match_is_not_support",
            "pane_text_is_not_recall_success",
            "support_bundle_is_not_full_topology_proof",
        ],
    }


def _bm25_search_vault(vault: Path, query: str, top_k: int = 20) -> list[dict] | None:
    bridge_script = Path(__file__).resolve().parent.parent / "bm25_search.py"
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
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
        return None


def run_consumer(mailbox: Path, vault: Path):
    """Read query intents from the mailbox and return Evidence Pack results.

    `build_ptc_retrieval_orchestrator_result` is the normal deterministic
    read-only path. The older BM25/lifecycle/edge path below is a compatibility
    fallback, not the recall route owner.
    """
    # ★ 14차 Axis 4: sandbox guard (보안 계층, 기능 블로커 아님)
    try:
        from runtime.sandbox import sandbox_run
        sandbox_ok = sandbox_run(["python3", "--version"], timeout=10)
        if sandbox_ok is None:
            log_event("sandbox_unavailable", reason="bwrap_not_found", action="continue_direct")
    except (ImportError, OSError, RuntimeError):
        log_event("sandbox_unavailable", reason="import_error", action="continue_direct")

    t0 = datetime.now(timezone.utc)

    queries_file = mailbox / "queries.jsonl"
    receipts_file = mailbox / "query_receipts.jsonl"

    if not queries_file.exists():
        print(json.dumps({"status": "no_queries"}))
        return

    vault_nodes = load_vault(vault)

    completed = set()
    if receipts_file.exists():
        for line in receipts_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line).get("in_reply_to"))
                row = json.loads(line)
                completed.add(row.get("mail_id"))
                completed.add(row.get("work_order_id"))

    for line in queries_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg["mail_id"] in completed:
            continue

        query_text = msg["payload"]["query_text"]
        receipt_delivery_id = msg.get("postman_delivery_id") or msg.get("delivery_id")

        # Phase 2: PTC path. The worker-authored program is a visible probe,
        # but the final answer must still be evidence-bound as a support bundle.
        if msg.get("payload", {}).get("ptc"):
            ptc_code = msg["payload"].get("ptc_code", "")
            ptc_result = {}
            pathfinder_plan = {}
            pathfinder_runtime = {}
            tst_supervisor_result = {}
            pathfinder_error = None
            if ptc_code.strip() and _ptc_exec:
                ptc_result = _ptc_exec(ptc_code, vault, mode="ipc", timeout=120)
            if build_memory_finder_tst_result is not None:
                try:
                    tst_supervisor_result = build_memory_finder_tst_result(
                        query_text=query_text,
                        vault_root=vault,
                        program_source=ptc_code,
                    )
                    pathfinder_plan = tst_supervisor_result.get("pathfinder_plan") or {}
                    pathfinder_runtime = tst_supervisor_result.get("pathfinder_runtime") or {}
                except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                    pathfinder_error = type(exc).__name__
            elif (
                build_query_adaptive_pathfinder_plan is not None
                and build_pathfinder_bundle_via_programmatic_tool_runtime is not None
            ):
                try:
                    pathfinder_plan = build_query_adaptive_pathfinder_plan(
                        query_text=query_text,
                        recent_limit=3,
                    )
                    runtime_result = build_pathfinder_bundle_via_programmatic_tool_runtime(
                        query_text=query_text,
                        vault_root=vault,
                        program=pathfinder_plan.get("json_tool_plan") or [],
                    )
                    trace = runtime_result.get("trace") or {}
                    pathfinder_runtime = {
                        "trace_ref": runtime_result.get("trace_ref"),
                        "final_result_ref": runtime_result.get("final_result_ref"),
                        "runtime_mode": trace.get("runtime_mode"),
                        "decision": trace.get("decision"),
                        "capability_registry_count": len(trace.get("capability_registry") or []),
                        "capability_calls": trace.get("capability_calls") or [],
                        "final_result": trace.get("final_result") or {},
                        "reason_codes": trace.get("reason_codes") or [],
                    }
                except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                    pathfinder_error = type(exc).__name__
            if build_ptc_retrieval_orchestrator_result is not None:
                try:
                    orchestrated = build_ptc_retrieval_orchestrator_result(
                        query_text=query_text,
                        vault_root=vault,
                        top_k=20,
                    )
                    bundle = dict(orchestrated["consumer_bundle"])
                    candidate_set = orchestrated.get("candidate_set") or {}
                    selected = candidate_set.get("selected_candidate_ids") or []
                    rejected = candidate_set.get("rejected_candidate_ids") or []
                    candidates = list(candidate_set.get("candidates") or [])
                    bundle["structured_recall_answer_frame"] = orchestrated.get(
                        "structured_recall_answer_frame"
                    )
                    bundle["candidate_reranker"] = {
                        "schema_version": "candidate_reranker_receipt_summary.v1",
                        "reranker_policy": candidate_set.get("reranker_policy"),
                        "selected_candidate_ids": selected,
                        "rejected_candidate_ids": rejected,
                        "selected": [
                            {
                                "candidate_id": candidate.get("candidate_id"),
                                "generator": candidate.get("generator"),
                                "source_path": candidate.get("source_path"),
                                "source_ref": candidate.get("source_ref"),
                                "candidate_feature_vector": candidate.get("candidate_feature_vector"),
                                "candidate_reranker": candidate.get("candidate_reranker"),
                            }
                            for candidate in candidates
                            if candidate.get("candidate_id") in set(selected)
                        ][:5],
                        "rejected_hard_gate_reasons": [
                            {
                                "candidate_id": candidate.get("candidate_id"),
                                "reason": candidate.get("rejection_reason"),
                                "hard_gate_reason_codes": (
                                    (
                                        candidate.get("candidate_reranker", {})
                                        .get("hard_gate_results", {})
                                        .get("reason_codes")
                                    )
                                    if isinstance(candidate.get("candidate_reranker"), dict)
                                    else []
                                ),
                            }
                            for candidate in candidates
                            if candidate.get("candidate_id") in set(rejected)
                        ][:10],
                    }
                    bundle["ptc_worker_program"] = {
                        "schema_version": "ptc_worker_program.v1",
                        "program_source": ptc_code[:2000],
                        "program_source_status": "worker_authored_probe_present"
                        if ptc_code.strip()
                        else "typed_unavailable_no_program_source",
                        "execution_status": ptc_result.get("status")
                        if ptc_result
                        else "typed_unavailable_ptc_executor_not_run",
                        "exit_code": ptc_result.get("exit_code") if ptc_result else None,
                        "sandbox": ptc_result.get("sandbox") if ptc_result else None,
                        "stdout_preview": (ptc_result.get("stdout", "") or "")[:1200]
                        if ptc_result
                        else "",
                        "stderr_preview": (ptc_result.get("stderr", "") or "")[:1200]
                        if ptc_result
                        else "",
                        "final_derivation_route": (
                            "tool_discovery_plan_plus_retrieval_orchestrator_support_bundle"
                        ),
                        "tool_discovery": {
                            "schema_version": "ptc_tool_discovery.v1",
                            "catalog_ref": "ptc-tool-registry-ref://openyggdrasil/pathfinder/v1",
                            "catalog_loaded_into_worker_context": False,
                            "context_policy": (
                                "Keep the full tool catalog out of the live context; "
                                "surface only selected tool ids, calls, hashes, and result refs."
                            ),
                            "selected_tool_ids": pathfinder_plan.get("tool_step_order") or [],
                            "selected_tool_count": len(pathfinder_plan.get("tool_step_order") or []),
                            "tool_references": (
                                (tst_supervisor_result.get("tst_supervisor") or {}).get("tool_references")
                                or []
                            ),
                            "planner_execution_mode": pathfinder_plan.get("planner_execution_mode"),
                            "strategy": pathfinder_plan.get("strategy"),
                            "reason_codes": pathfinder_plan.get("reason_codes") or [],
                            "typed_unavailable": {
                                "schema_version": "typed_unavailable.v1",
                                "reason_code": pathfinder_error,
                            }
                            if pathfinder_error
                            else None,
                        },
                        "bounded_program": {
                            "schema_version": "ptc_bounded_program.v1",
                            "program_kind": "bounded_json_tool_plan",
                            "dynamic_code_execution_allowed": False,
                            "program_source_status": pathfinder_plan.get("program_source_status"),
                            "json_tool_plan": pathfinder_plan.get("json_tool_plan") or [],
                            "execution_status": pathfinder_runtime.get("decision")
                            or (
                                "typed_unavailable_program_runtime_not_completed"
                                if pathfinder_error
                                else "typed_unavailable_program_runtime_not_invoked"
                            ),
                            "trace_ref": pathfinder_runtime.get("trace_ref"),
                            "final_result_ref": pathfinder_runtime.get("final_result_ref"),
                            "capability_registry_count": pathfinder_runtime.get(
                                "capability_registry_count", 0
                            ),
                            "capability_calls": pathfinder_runtime.get("capability_calls") or [],
                            "reason_codes": pathfinder_runtime.get("reason_codes") or [],
                        },
                        "tst_supervisor": (tst_supervisor_result.get("tst_supervisor") or None),
                        "tst_capability_supervisor": (
                            tst_supervisor_result.get("tst_capability_supervisor")
                            or tst_supervisor_result.get("tst_supervisor")
                            or None
                        ),
                        "candidate_count": len(candidate_set.get("candidates") or []),
                        "selected_candidate_count": len(selected),
                        "rejected_candidate_count": len(rejected),
                        "coverage_state": candidate_set.get("coverage_state"),
                        "retry_decision": candidate_set.get("retry_decision"),
                        "hard_nonclaims": [
                            "stdout_alone_is_not_support_bundle",
                            "full_tool_catalog_not_loaded_into_model_context",
                            "not_arbitrary_write_enabled_code_execution",
                            "not_full_ux_pass",
                        ],
                    }
                    bundle, receipt_status = _prepare_memory_finder_bundle_with_fallback(
                        query_text=query_text,
                        bundle=bundle,
                        status="completed",
                        vault=vault,
                    )
                    worker_judgment = _memory_finder_judgment(
                        query_text=query_text,
                        bundle=bundle,
                        status=receipt_status,
                    )
                    bundle["worker_judgment"] = worker_judgment
                    write_operator_receipt(
                        receipts_file,
                        msg["mail_id"],
                        status=receipt_status,
                        bundle=bundle,
                        worker_judgment=worker_judgment,
                        consumer_pid=os.getpid(),
                        delivery_id=receipt_delivery_id,
                    )
                    deliver_receipt(mailbox, msg["mail_id"], status=receipt_status, result_bundle=bundle)
                    continue
                except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                    log_event("ptc_retrieval_orchestrator_skip", reason=type(exc).__name__)
            stdout = (ptc_result.get("stdout", "") or "")[:3000] if ptc_result else ""
            degraded_bundle = {
                "ptc_stdout": stdout,
                "mode": "ptc_degraded_stdout_only",
                "typed_unavailable": {
                    "schema_version": "typed_unavailable.v1",
                    "reason_code": "ptc_support_bundle_derivation_unavailable",
                },
            }
            degraded_bundle, degraded_status = _prepare_memory_finder_bundle(
                query_text=query_text,
                bundle=degraded_bundle,
                status="typed_unavailable_support_bundle_derivation_unavailable",
            )
            degraded_judgment = _memory_finder_judgment(
                query_text=query_text,
                bundle=degraded_bundle,
                status=degraded_status,
            )
            degraded_bundle["worker_judgment"] = degraded_judgment
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status=degraded_status,
                bundle=degraded_bundle,
                worker_judgment=degraded_judgment,
                consumer_pid=os.getpid(),
                delivery_id=receipt_delivery_id,
            )
            deliver_receipt(mailbox, msg["mail_id"], status=degraded_status, result_bundle=degraded_bundle)
            continue

        # Deterministic read-only PTC retrieval orchestrator. BM25 is one
        # candidate generator here, not the owner of the retrieval route.
        if build_ptc_retrieval_orchestrator_result is not None:
            try:
                orchestrated = build_ptc_retrieval_orchestrator_result(
                    query_text=query_text,
                    vault_root=vault,
                    top_k=20,
                )
                bundle = dict(orchestrated["consumer_bundle"])
                if build_memory_finder_tst_result is not None:
                    try:
                        tst_result = build_memory_finder_tst_result(
                            query_text=query_text,
                            vault_root=vault,
                            program_source="",
                        )
                        bundle["tst_capability_supervisor"] = (
                            tst_result.get("tst_capability_supervisor")
                            or tst_result.get("tst_supervisor")
                            or None
                        )
                    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                        bundle["tst_capability_supervisor"] = {
                            "schema_version": "tst_capability_supervisor.v1",
                            "status": "typed_unavailable",
                            "reason_code": type(exc).__name__,
                        }
                bundle, receipt_status = _prepare_memory_finder_bundle_with_fallback(
                    query_text=query_text,
                    bundle=bundle,
                    status="completed",
                    vault=vault,
                )
                worker_judgment = _memory_finder_judgment(
                    query_text=query_text,
                    bundle=bundle,
                    status=receipt_status,
                )
                bundle["worker_judgment"] = worker_judgment
                write_operator_receipt(
                    receipts_file,
                    msg["mail_id"],
                    status=receipt_status,
                    bundle=bundle,
                    worker_judgment=worker_judgment,
                    consumer_pid=os.getpid(),
                    delivery_id=receipt_delivery_id,
                )
                deliver_receipt(mailbox, msg["mail_id"], status=receipt_status, result_bundle=bundle)
                continue
            except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                log_event("ptc_retrieval_orchestrator_skip", reason=type(exc).__name__)

        # 고정 경로
        bm25_results = _bm25_search_vault(vault, query_text, top_k=20)
        if bm25_results is not None and len(bm25_results) > 0:
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
            matches = search_vault_bm25(vault_nodes, query_text)

        matches = [m for m in matches if m.get("metadata", {}).get("status", "").upper() == "ACTIVE"]
        edges = load_edges(vault)
        matches = _boost_by_edges(matches, edges)

        # Legacy advisory hint only; provider-facing support must still come
        # from a typed bundle or typed_unavailable result.
        if _ptc_exec and query_text:
            try:
                ptc_result = _ptc_exec(
                    code=f'deep_search("{query_text}", max_depth=2, limit=10)',
                    vault=vault, mode="ipc", timeout=15,
                )
                stdout = ptc_result.get("stdout", "")
                if stdout:
                    try:
                        import json as _json
                        parsed = _json.loads(stdout.strip().split("\n")[-1])
                        ptc_trail = parsed.get("result", {}).get("trail", [])
                        if ptc_trail:
                            log_event("ptc_deep_search_hint",
                                      visited=parsed["result"].get("visited"),
                                      depth=parsed["result"].get("depth_reached"))
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
            except (OSError, RuntimeError, ValueError, TypeError):
                pass

        bundle = format_consumer_result(query_text, matches)
        if build_ring_support_bundle is not None:
            try:
                ring_bundle = build_ring_support_bundle(
                    query_text=query_text,
                    vault_root=vault,
                    matched_nodes=matches,
                )
                if ring_bundle.get("ring_ids") or ring_bundle.get("typed_unavailable"):
                    if bundle.get("korean_query_expansion"):
                        ring_bundle["korean_query_expansion"] = bundle["korean_query_expansion"]
                    bundle["support_bundle"] = ring_bundle
            except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                log_event("ring_support_bundle_skip", reason=type(exc).__name__)
        bundle, receipt_status = _prepare_memory_finder_bundle_with_fallback(
            query_text=query_text,
            bundle=bundle,
            status="completed",
            vault=vault,
        )
        worker_judgment = _memory_finder_judgment(
            query_text=query_text,
            bundle=bundle,
            status=receipt_status,
        )
        bundle["worker_judgment"] = worker_judgment
        write_operator_receipt(
            receipts_file,
            msg["mail_id"],
            status=receipt_status,
            bundle=bundle,
            worker_judgment=worker_judgment,
            consumer_pid=os.getpid(),
            delivery_id=receipt_delivery_id,
        )
        deliver_receipt(mailbox, msg["mail_id"], status=receipt_status, result_bundle=bundle)

    print(json.dumps({"status": "consumer_done", "pid": os.getpid(),
                       "elapsed_ms": round((datetime.now(timezone.utc) - t0).total_seconds() * 1000)}))
