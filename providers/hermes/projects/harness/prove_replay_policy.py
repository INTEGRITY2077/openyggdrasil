from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import harness_common
import replay_failed_job
from harness_common import OPS_ROOT, build_job, enqueue_job, read_jsonl, record_event


PROJECT_ROOT = Path(__file__).resolve().parent
PROOF_OUTPUT_PATH = OPS_ROOT / "replay-policy-proof.json"


def patch_queue_roots(base_dir: Path) -> None:
    ops_root = base_dir / "ops"
    queue_root = ops_root / "queue"
    locks_root = ops_root / "locks"
    harness_common.OPS_ROOT = ops_root
    harness_common.QUEUE_ROOT = queue_root
    harness_common.LOCKS_ROOT = locks_root
    harness_common.JOBS_PATH = queue_root / "jobs.jsonl"
    harness_common.EVENTS_PATH = queue_root / "worker-events.jsonl"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="replay-policy-proof-") as tmp:
        patch_queue_roots(Path(tmp))

        failed_job = build_job(
            "promotion",
            {"profile": "wiki", "session_id": "session-proof"},
            requested_by="proof",
            parent_question_id="question-proof",
        )
        enqueue_job(failed_job)
        record_event(
            "job_failed",
            {"job_id": failed_job["job_id"], "job_type": failed_job["job_type"], "error": "proof failure"},
        )

        replay_failed_job.parse_args = lambda: argparse.Namespace(
            job_id=failed_job["job_id"],
            latest_failed=False,
            requested_by="proof-replay",
            max_replay_depth=2,
        )
        replay_failed_job.main()

        jobs = read_jsonl(harness_common.JOBS_PATH)
        events = read_jsonl(harness_common.EVENTS_PATH)
        replay_job = jobs[-1]
        replay_event = next(event for event in reversed(events) if event.get("event_type") == "job_replayed")

        succeeded_job = build_job(
            "promotion",
            {"profile": "wiki", "session_id": "session-succeeded"},
            requested_by="proof",
            parent_question_id="question-proof",
        )
        enqueue_job(succeeded_job)
        record_event("job_succeeded", {"job_id": succeeded_job["job_id"], "job_type": succeeded_job["job_type"]})

        blocked_error = None
        replay_failed_job.parse_args = lambda: argparse.Namespace(
            job_id=succeeded_job["job_id"],
            latest_failed=False,
            requested_by="proof-replay",
            max_replay_depth=2,
        )
        try:
            replay_failed_job.main()
        except RuntimeError as exc:
            blocked_error = str(exc)

        blocked_event = next(
            (event for event in reversed(read_jsonl(harness_common.EVENTS_PATH)) if event.get("event_type") == "job_replay_blocked"),
            None,
        )

        ok = (
            replay_job.get("replayed_from") == failed_job["job_id"]
            and replay_job.get("replay_root_job_id") == failed_job["job_id"]
            and replay_job.get("replay_depth") == 1
            and replay_job.get("parent_question_id") == "question-proof"
            and replay_event.get("event_type") == "job_replayed"
            and replay_event.get("replay_depth") == 1
            and blocked_event is not None
            and blocked_event.get("job_id") == succeeded_job["job_id"]
            and blocked_error is not None
            and "not replayable" in blocked_error
        )

        payload = {
            "status": "ok" if ok else "failed",
            "queue_root": str(harness_common.QUEUE_ROOT),
            "failed_job_id": failed_job["job_id"],
            "replay_job_id": replay_job["job_id"],
            "replay_job": replay_job,
            "replay_event": replay_event,
            "blocked_event": blocked_event,
            "blocked_error": blocked_error,
        }
        PROOF_OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
