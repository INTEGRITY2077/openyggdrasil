from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from graph_freshness import mark_sot_write
from harness_common import file_lock
from worker_runtime import record_worker_event


PROJECTS_ROOT = Path(__file__).resolve().parents[1]
PROMOTION_SCRIPT = PROJECTS_ROOT / "wiki-promotion" / "promote_transcript_to_query.py"


def python_command(script: Path, args: List[str]) -> List[str]:
    return ["py", "-3", str(script), *args]


def run_subprocess(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def execute_promotion(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job["payload"]
    args: List[str] = []
    if payload.get("profile"):
        args.extend(["--profile", payload["profile"]])
    if payload.get("session_id"):
        args.extend(["--session-id", payload["session_id"]])
    if payload.get("session_json"):
        args.extend(["--session-json", payload["session_json"]])
    if payload.get("refresh_transcript"):
        args.append("--refresh-transcript")
    if payload.get("placement_verdict"):
        encoded = base64.b64encode(
            json.dumps(payload["placement_verdict"], ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        args.extend(["--placement-verdict-base64", encoded])

    with file_lock("promotion"):
        result = run_subprocess(python_command(PROMOTION_SCRIPT, args))

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "promotion failed")

    record_worker_event(
        "promotion_completed",
        {
            "job_id": job["job_id"],
            "stdout": result.stdout.strip(),
        },
    )
    freshness = mark_sot_write(
        job_id=job["job_id"],
        parent_question_id=job.get("parent_question_id"),
    )
    record_worker_event(
        "graph_freshness_marked_stale",
        {
            "job_id": job["job_id"],
            "freshness_status": freshness["status"],
            "reasons": freshness["reasons"],
        },
    )

    return {
        "stdout": result.stdout.strip(),
        "chained_graph_payload": payload.get("graph_rebuild_payload") if payload.get("enqueue_graph_rebuild") else None,
    }
