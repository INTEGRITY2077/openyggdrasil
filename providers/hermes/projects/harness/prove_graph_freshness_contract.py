from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import deep_search_executor
import graph_freshness
from harness_common import OPS_ROOT


PROOF_OUTPUT_PATH = OPS_ROOT / "graph-freshness-proof.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="graph-freshness-proof-") as tmpdir:
        root = Path(tmpdir)
        vault = root / "vault"
        vault.mkdir()
        summary = root / "graphify-out" / "summary.json"
        summary.parent.mkdir(parents=True)
        state_path = root / "graph-freshness.json"

        # stale phase: summary exists first, then vault changes later
        summary.write_text(json.dumps({"nodes": 1}, indent=2), encoding="utf-8")
        time.sleep(0.02)
        note = vault / "queries" / "mailbox-reverse-push.md"
        note.parent.mkdir(parents=True)
        note.write_text("# Mailbox Reverse Push\n\nThe result is picked up on the next safe turn.\n", encoding="utf-8")

        stale_status = graph_freshness.current_graph_freshness(
            vault_root=vault,
            summary_path=summary,
            state_path=state_path,
        )

        original_vault_root = deep_search_executor.VAULT_ROOT
        original_current_freshness = deep_search_executor.current_graph_freshness
        original_run_graphify_query = deep_search_executor.run_graphify_query
        try:
            deep_search_executor.VAULT_ROOT = vault
            deep_search_executor.current_graph_freshness = lambda **kwargs: graph_freshness.current_graph_freshness(
                vault_root=vault,
                summary_path=summary,
                state_path=state_path,
            )

            def fail_query(question: str) -> str:
                raise RuntimeError("Graphify query should not run while stale")

            deep_search_executor.run_graphify_query = fail_query
            stale_result = deep_search_executor.execute_deep_search(
                profile="wiki",
                session_id="freshness-proof-stale",
                question="How does the mailbox reverse push flow work?",
                parent_question_id="question-freshness-proof",
                mailbox_namespace="proof-graph-freshness-stale",
            )

            # fresh phase: record rebuild after fresh summary write
            time.sleep(0.02)
            summary.write_text(json.dumps({"nodes": 2}, indent=2), encoding="utf-8")
            fresh_status = graph_freshness.mark_graph_rebuild(
                job_id="graph-proof-1",
                parent_question_id="question-freshness-proof",
                vault_root=vault,
                summary_path=summary,
                state_path=state_path,
            )

            deep_search_executor.run_graphify_query = lambda question: "graph_line_one\ngraph_line_two"
            fresh_result = deep_search_executor.execute_deep_search(
                profile="wiki",
                session_id="freshness-proof-fresh",
                question="How does the mailbox reverse push flow work?",
                parent_question_id="question-freshness-proof",
                mailbox_namespace="proof-graph-freshness-fresh",
            )
        finally:
            deep_search_executor.VAULT_ROOT = original_vault_root
            deep_search_executor.current_graph_freshness = original_current_freshness
            deep_search_executor.run_graphify_query = original_run_graphify_query

        payload = {
            "status": "ok",
            "stale_status": stale_status,
            "stale_packet_freshness": stale_result["packet"]["payload"]["graph_freshness"],
            "stale_packet_fact_preview": stale_result["packet"]["payload"]["facts"][:2],
            "fresh_status": fresh_status,
            "fresh_packet_freshness": fresh_result["packet"]["payload"]["graph_freshness"],
            "fresh_packet_fact_preview": fresh_result["packet"]["payload"]["facts"][:2],
        }
        if stale_status["status"] != "stale":
            raise RuntimeError("stale phase did not report stale")
        if stale_result["packet"]["payload"]["graph_freshness"]["graph_query_used"] is not False:
            raise RuntimeError("stale phase still trusted Graphify")
        if fresh_status["status"] != "fresh":
            raise RuntimeError("fresh phase did not report fresh")
        if fresh_result["packet"]["payload"]["graph_freshness"]["graph_query_used"] is not True:
            raise RuntimeError("fresh phase did not trust Graphify")

        PROOF_OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
