from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from subagent_telemetry import TELEMETRY_EVENTS_PATH


PROJECT_ROOT = Path(__file__).resolve().parent
LIFECYCLE_ORCHESTRATOR = PROJECT_ROOT / "lifecycle_orchestrator.py"
EMIT_DEEP_SEARCH = PROJECT_ROOT / "emit_deep_search_command.py"
PREFLIGHT = PROJECT_ROOT / "hermes_preflight_consume.py"


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


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove end-to-end observer -> postman -> preflight lifecycle.")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_id = f"e2e-poc-{uuid.uuid4().hex[:8]}"
    mailbox_namespace = f"proof-{session_id}"
    parent_question_id = f"question-{session_id}"
    question = "How does the external harness relate to the mailbox reverse push flow?"

    deep_search_command = json.loads(
        run_py(
            EMIT_DEEP_SEARCH,
            [
                "--profile",
                "wiki",
                "--session-id",
                session_id,
                "--mailbox-namespace",
                mailbox_namespace,
                "--parent-question-id",
                parent_question_id,
                "--question",
                question,
            ],
        )
    )
    orchestrator_summary = json.loads(
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
                "e2e-poc",
            ],
        )
    )
    preflight_packets = json.loads(
        run_py(
            PREFLIGHT,
            [
                "--profile",
                "wiki",
                "--session-id",
                session_id,
                "--mailbox-namespace",
                mailbox_namespace,
                "--query",
                question,
                "--top-k",
                "3",
                "--parent-question-id",
                parent_question_id,
            ],
        )
    )
    telemetry_rows = [row for row in read_jsonl(TELEMETRY_EVENTS_PATH) if row.get("parent_question_id") == parent_question_id]

    result = {
        "status": "ok",
        "session_id": session_id,
        "mailbox_namespace": mailbox_namespace,
        "parent_question_id": parent_question_id,
        "question": question,
        "deep_search_command_id": deep_search_command["message_id"],
        "deep_search_command_parent_question_id": deep_search_command.get("parent_question_id"),
        "orchestrator_summary": orchestrator_summary,
        "preflight_packet_count": len(preflight_packets),
        "preflight_message_types": [packet.get("message_type") for packet in preflight_packets],
        "preflight_message_ids": [packet.get("message_id") for packet in preflight_packets],
        "preflight_parent_question_ids": sorted(
            {packet.get("parent_question_id") for packet in preflight_packets if packet.get("parent_question_id")}
        ),
        "telemetry_roles_for_parent_question": sorted({row.get("role") for row in telemetry_rows if row.get("role")}),
        "telemetry_actions_for_parent_question": sorted({row.get("action") for row in telemetry_rows if row.get("action")}),
        "telemetry_event_count_for_parent_question": len(telemetry_rows),
    }
    if result["deep_search_command_parent_question_id"] != parent_question_id:
        raise RuntimeError("deep search command lost parent_question_id")
    if parent_question_id not in result["preflight_parent_question_ids"]:
        raise RuntimeError("preflight packets did not preserve the originating parent_question_id")
    required_actions = {"command_routed", "push_delivered", "preflight_packet_consumed"}
    if not required_actions.issubset(set(result["telemetry_actions_for_parent_question"])):
        raise RuntimeError("parent_question_id telemetry flow is incomplete")
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
