"""
Memory Finder consumer runtime.

The primary recall route is the deterministic read-only PTC retrieval
orchestrator. Legacy BM25/lifecycle/edge search remains only as a degraded
fallback when the orchestrator is unavailable.
"""
from __future__ import annotations

import json
import os
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

    for line in queries_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg["mail_id"] in completed:
            continue

        query_text = msg["payload"]["query_text"]

        # Phase 2: PTC path. The worker-authored program is a visible probe,
        # but the final answer must still be evidence-bound as a support bundle.
        if msg.get("payload", {}).get("ptc"):
            ptc_code = msg["payload"].get("ptc_code", "")
            ptc_result = {}
            pathfinder_plan = {}
            pathfinder_runtime = {}
            pathfinder_error = None
            if ptc_code.strip() and _ptc_exec:
                ptc_result = _ptc_exec(ptc_code, vault, mode="ipc", timeout=120)
            if (
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
                    bundle["structured_recall_answer_frame"] = orchestrated.get(
                        "structured_recall_answer_frame"
                    )
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
                    write_operator_receipt(
                        receipts_file,
                        msg["mail_id"],
                        status="completed",
                        bundle=bundle,
                        consumer_pid=os.getpid(),
                    )
                    deliver_receipt(mailbox, msg["mail_id"], status="completed", result_bundle=bundle)
                    continue
                except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                    log_event("ptc_retrieval_orchestrator_skip", reason=type(exc).__name__)
            stdout = (ptc_result.get("stdout", "") or "")[:3000] if ptc_result else ""
            write_operator_receipt(
                receipts_file,
                msg["mail_id"],
                status="completed",
                bundle={
                    "ptc_stdout": stdout,
                    "mode": "ptc_degraded_stdout_only",
                    "typed_unavailable": {
                        "schema_version": "typed_unavailable.v1",
                        "reason_code": "ptc_support_bundle_derivation_unavailable",
                    },
                },
                consumer_pid=os.getpid(),
            )
            deliver_receipt(mailbox, msg["mail_id"], status="completed",
                           result_bundle={"ptc_stdout": stdout[:500]})
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
                bundle = orchestrated["consumer_bundle"]
                write_operator_receipt(
                    receipts_file,
                    msg["mail_id"],
                    status="completed",
                    bundle=bundle,
                    consumer_pid=os.getpid(),
                )
                deliver_receipt(mailbox, msg["mail_id"], status="completed", result_bundle=bundle)
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
        write_operator_receipt(
            receipts_file,
            msg["mail_id"],
            status="completed",
            bundle=bundle,
            consumer_pid=os.getpid(),
        )
        deliver_receipt(mailbox, msg["mail_id"], status="completed", result_bundle=bundle)

    print(json.dumps({"status": "consumer_done", "pid": os.getpid(),
                       "elapsed_ms": round((datetime.now(timezone.utc) - t0).total_seconds() * 1000)}))
