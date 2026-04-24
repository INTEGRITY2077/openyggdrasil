from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from harness_common import EVENTS_PATH, LOCKS_ROOT, OPS_ROOT, read_jsonl


PROJECT_ROOT = Path(__file__).resolve().parent
RUN_DAEMON_SCRIPT = PROJECT_ROOT / "run_daemon.py"
PROOF_OUTPUT_PATH = OPS_ROOT / "daemon-hardening-proof.json"


def main() -> int:
    proof_lock = LOCKS_ROOT / "daemon-proof.lock"
    status_path = OPS_ROOT / "queue" / "daemon-proof-status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    LOCKS_ROOT.mkdir(parents=True, exist_ok=True)
    status_path.unlink(missing_ok=True)
    proof_lock.write_text(
        json.dumps(
            {
                "lock": "daemon-proof",
                "pid": 999999,
                "host": "proof-host",
                "created_at": "2026-04-21T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    before_events = read_jsonl(EVENTS_PATH)
    before_count = len(before_events)
    command = [
        sys.executable,
        str(RUN_DAEMON_SCRIPT),
        "--iterations",
        "1",
        "--interval-seconds",
        "0",
        "--skip-discovery",
        "--skip-worker",
        "--requested-by",
        "daemon-proof",
        "--stale-lock-age-seconds",
        "60",
        "--status-path",
        str(status_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    after_events = read_jsonl(EVENTS_PATH)
    new_events = after_events[before_count:]
    event_types = [str(event.get("event_type") or "") for event in new_events]
    status_payload: Dict[str, Any] = json.loads(status_path.read_text(encoding="utf-8"))
    daemon_summary: Dict[str, Any] = json.loads(completed.stdout.strip() or "{}")

    ok = (
        completed.returncode == 0
        and not proof_lock.exists()
        and status_path.exists()
        and status_payload.get("active") is False
        and status_payload.get("cycles") == 1
        and "daemon_stale_locks_recovered" in event_types
        and "daemon_heartbeat" in event_types
        and "daemon_stopped" in event_types
        and daemon_summary.get("stop_reason") == "iterations_complete"
    )

    payload = {
        "status": "ok" if ok else "failed",
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "proof_lock_removed": not proof_lock.exists(),
        "status_path": str(status_path),
        "status_payload": status_payload,
        "daemon_summary": daemon_summary,
        "new_event_types": event_types,
    }
    PROOF_OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
