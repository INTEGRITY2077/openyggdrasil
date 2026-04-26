from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from emit_push_poc import default_facts, resolve_source_paths
from mailbox_poc import emit_graph_hint_poc
from postman_push_once import deliver_once
from run_worker import process_job
from subagent_telemetry import TELEMETRY_EVENTS_PATH


CENTRAL_ROOT = Path(__file__).resolve().parents[2]
OPENYGGDRASIL_ROOT = CENTRAL_ROOT.parents[1]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove subagent telemetry traceability.")
    parser.add_argument("--profile", default="wiki")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = time.time()
    session_id = f"telemetry-poc-{uuid.uuid4().hex[:8]}"
    mailbox_namespace = f"proof-{session_id}"
    topic = "subagent telemetry traceability"
    parent_question_id = f"question-{session_id}"

    packet = emit_graph_hint_poc(
        profile=args.profile,
        session_id=session_id,
        mailbox_namespace=mailbox_namespace,
        parent_question_id=parent_question_id,
        topic=topic,
        source_paths=resolve_source_paths(None),
        facts=default_facts(),
        human_summary="Telemetry proof packet emitted for observer/postman trace validation.",
    )

    delivery = deliver_once(
        argparse.Namespace(
            profile=args.profile,
            session_id=session_id,
            limit=1,
            mailbox_namespace=mailbox_namespace,
        )
    )

    graph_job = {
        "job_id": f"telemetry-graph-{uuid.uuid4().hex}",
        "job_type": "graph_rebuild",
        "parent_question_id": parent_question_id,
        "payload": {
            "vault": CENTRAL_ROOT / "vault",
            "sandbox_root": OPENYGGDRASIL_ROOT / ".runtime" / "graphify",
            "manifest": OPENYGGDRASIL_ROOT / "common" / "graphify" / "graphify-corpus.manifest.json",
            "refresh_semantic": False,
            "directed": False,
        },
    }
    process_job(graph_job)

    telemetry_rows = [
        row
        for row in read_jsonl(TELEMETRY_EVENTS_PATH)
        if row.get("timestamp") and row.get("timestamp")
    ]
    packet_trace = [row for row in telemetry_rows if row.get("trace_id") == packet["message_id"]]
    graph_trace = [row for row in telemetry_rows if row.get("trace_id") == graph_job["job_id"]]

    result = {
        "status": "ok",
        "profile": args.profile,
        "session_id": session_id,
        "packet_message_id": packet["message_id"],
        "mailbox_namespace": mailbox_namespace,
        "parent_question_id": parent_question_id,
        "delivery": delivery,
        "graph_job_id": graph_job["job_id"],
        "telemetry_path": str(TELEMETRY_EVENTS_PATH),
        "observer_trace_roles": sorted({row["role"] for row in packet_trace}),
        "observer_trace_actors": sorted({row["actor"] for row in packet_trace}),
        "observer_trace_deciders": sorted({row["decider"] for row in packet_trace}),
        "observer_trace_producers": sorted({row["producer"] for row in packet_trace}),
        "observer_trace_actions": sorted({row["action"] for row in packet_trace}),
        "observer_trace_parent_question_ids": sorted({row["parent_question_id"] for row in packet_trace}),
        "graph_trace_roles": sorted({row["role"] for row in graph_trace}),
        "graph_trace_actors": sorted({row["actor"] for row in graph_trace}),
        "graph_trace_deciders": sorted({row["decider"] for row in graph_trace}),
        "graph_trace_producers": sorted({row["producer"] for row in graph_trace}),
        "graph_trace_actions": sorted({row["action"] for row in graph_trace}),
        "graph_trace_parent_question_ids": sorted({row["parent_question_id"] for row in graph_trace}),
        "packet_trace_count": len(packet_trace),
        "graph_trace_count": len(graph_trace),
        "duration_seconds": round(time.time() - started_at, 2),
    }

    if "observer" not in result["observer_trace_actors"] or "postman" not in result["observer_trace_actors"]:
        raise RuntimeError("packet trace missing expected observer/postman actors")
    if result["graph_trace_actors"] != ["graph_builder"]:
        raise RuntimeError("graph trace actor should be graph_builder")
    if result["graph_trace_deciders"] != ["command-worker"]:
        raise RuntimeError("graph trace decider should be command-worker")
    if result["observer_trace_parent_question_ids"] != [parent_question_id]:
        raise RuntimeError("packet trace parent_question_id should stay correlated")
    if result["graph_trace_parent_question_ids"] != [parent_question_id]:
        raise RuntimeError("graph trace parent_question_id should stay correlated")

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
