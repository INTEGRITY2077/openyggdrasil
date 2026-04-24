from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from harness_common import OPS_ROOT
from plugin_logger import PLUGIN_LOG_EVENTS_PATH, read_plugin_events


PROJECT_ROOT = Path(__file__).resolve().parent
EMIT_DEEP_SEARCH = PROJECT_ROOT / "emit_deep_search_command.py"
LIFECYCLE_ORCHESTRATOR = PROJECT_ROOT / "lifecycle_orchestrator.py"
PREFLIGHT = PROJECT_ROOT / "hermes_preflight_consume.py"
PROOF_OUTPUT_PATH = OPS_ROOT / "plugin-logger-proof.json"


def run_py(script: Path, args: list[str]) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return completed.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove plugin-plane dedicated logger coverage.")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_id = f"plugin-log-{uuid.uuid4().hex[:8]}"
    parent_question_id = f"question-{session_id}"
    mailbox_namespace = f"proof-{session_id}"
    question = "How does the plugin plane narrow an answer before Hermes responds?"

    run_py(
        EMIT_DEEP_SEARCH,
        [
            "--profile",
            "wiki",
            "--session-id",
            session_id,
            "--parent-question-id",
            parent_question_id,
            "--mailbox-namespace",
            mailbox_namespace,
            "--question",
            question,
        ],
    )
    run_py(
        LIFECYCLE_ORCHESTRATOR,
        [
            "--profiles",
            "wiki",
            "--schedule-lint",
            "--route-commands",
            "--deliver-packets",
            "--mailbox-namespace",
            mailbox_namespace,
            "--requested-by",
            "plugin-logger-proof",
        ],
    )
    preflight = json.loads(
        run_py(
            PREFLIGHT,
            [
                "--profile",
                "wiki",
                "--session-id",
                session_id,
                "--parent-question-id",
                parent_question_id,
                "--mailbox-namespace",
                mailbox_namespace,
                "--query",
                question,
                "--render-brief",
                "--render-answer",
            ],
        )
    )

    all_rows = read_plugin_events(path=PLUGIN_LOG_EVENTS_PATH)
    logger_rows = []
    for row in all_rows:
        artifacts = row.get("artifacts", {})
        if artifacts.get("mailbox_namespace") == mailbox_namespace:
            logger_rows.append(row)
            continue
        if row.get("parent_question_id") == parent_question_id:
            logger_rows.append(row)
    event_types = [row.get("event_type") for row in logger_rows]
    question_lineage_event_types = [
        row.get("event_type")
        for row in logger_rows
        if row.get("parent_question_id") == parent_question_id
    ]
    ok = {
        "deep_search_command_emitted",
        "observer_command_emitted",
        "command_routed",
        "graph_hint_generated",
        "lint_alert_generated",
        "packet_delivered",
        "preflight_selection_made",
        "decision_log_rendered",
        "answer_rendered",
        "answer_assurance_applied",
        "answer_quality_evaluated",
    }.issubset(set(event_types))

    answer_quality_row = next(
        (row for row in reversed(logger_rows) if row.get("event_type") == "answer_quality_evaluated"),
        None,
    )
    answer_assurance_row = next(
        (row for row in reversed(logger_rows) if row.get("event_type") == "answer_assurance_applied"),
        None,
    )

    payload = {
        "status": "ok" if ok else "failed",
        "plugin_log_path": str(PLUGIN_LOG_EVENTS_PATH),
        "parent_question_id": parent_question_id,
        "session_id": session_id,
        "mailbox_namespace": mailbox_namespace,
        "event_count": len(logger_rows),
        "event_types": event_types,
        "question_lineage_event_types": question_lineage_event_types,
        "preflight_rendering_mode": preflight.get("report", {}).get("rendering_mode"),
        "initial_answer_rendering_mode": preflight.get("initial_answer", {}).get("rendering_mode"),
        "answer_rendering_mode": preflight.get("answer", {}).get("rendering_mode"),
        "answer_hash": preflight.get("answer", {}).get("answer_hash"),
        "answer_assurance_mode": (answer_assurance_row or {}).get("artifacts", {}).get("assurance_mode"),
        "answer_quality_grade": (answer_quality_row or {}).get("state", {}).get("quality_grade"),
        "answer_unsupported_claim_risk": (answer_quality_row or {}).get("state", {}).get("unsupported_claim_risk"),
        "preflight_packet_types": [packet.get("message_type") for packet in preflight.get("packets", [])],
    }
    output_path = args.output or PROOF_OUTPUT_PATH
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
