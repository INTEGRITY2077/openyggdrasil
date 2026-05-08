"""
Operator Consumer — 14차 Axis 3: operator_entrypoint.py에서 분리.

run_consumer + _bm25_search_vault + PTC 대체 경로 (Phase 2)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ptc.primitives import (
    search_vault_bm25,
    format_consumer_result,
    load_vault,
    load_edges,
    _boost_by_edges,
)

from .helpers import deliver_receipt

from runtime.log_event import log_event

try:
    from runtime.retrieval.pathfinder_tools import build_ring_support_bundle
except Exception:
    build_ring_support_bundle = None

try:
    from runtime.retrieval.ptc_retrieval_orchestrator import build_ptc_retrieval_orchestrator_result
except Exception:
    build_ptc_retrieval_orchestrator_result = None

# PTC advisory import (lazy)
try:
    from runtime.ptc.sandbox_executor import execute_ptc_code as _ptc_exec
except Exception:
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
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, Exception):
        return None


def run_consumer(mailbox: Path, vault: Path):
    """Mailbox에서 query-intent를 폴링하여 Vault 검색 결과 반환.

    payload.ptc=true → PTC 경로 (LLM 코드가 Pathfinder 직접 구성)
    payload.ptc=false/없음 → 고정 경로 (기존 BM25→Lifecycle→Edge Boost)
    """
    # ★ 14차 Axis 4: sandbox guard (보안 계층, 기능 블로커 아님)
    try:
        from runtime.sandbox import sandbox_run
        sandbox_ok = sandbox_run(["python3", "--version"], timeout=10)
        if sandbox_ok is None:
            log_event("sandbox_unavailable", reason="bwrap_not_found", action="continue_direct")
    except Exception:
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

        # Phase 2: PTC 대체 경로
        if msg.get("payload", {}).get("ptc"):
            ptc_code = msg["payload"].get("ptc_code", "")
            if ptc_code.strip() and _ptc_exec:
                ptc_result = _ptc_exec(ptc_code, vault, mode="ipc", timeout=120)
                stdout = (ptc_result.get("stdout", "") or "")[:3000]
                receipt = {
                    "receipt_id": str(uuid.uuid4())[:8],
                    "in_reply_to": msg["mail_id"],
                    "status": "completed",
                    "bundle": {"ptc_stdout": stdout, "mode": "ptc"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "consumer_pid": os.getpid(),
                }
                with open(receipts_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(receipt, ensure_ascii=False) + "\n")
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
                deliver_receipt(mailbox, msg["mail_id"], status="completed", result_bundle=bundle)
                continue
            except Exception as exc:
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

        # PTC Advisory
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
                    except Exception:
                        pass
            except Exception:
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
            except Exception as exc:
                log_event("ring_support_bundle_skip", reason=type(exc).__name__)
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
        deliver_receipt(mailbox, msg["mail_id"], status="completed", result_bundle=bundle)

    print(json.dumps({"status": "consumer_done", "pid": os.getpid(),
                       "elapsed_ms": round((datetime.now(timezone.utc) - t0).total_seconds() * 1000)}))
