from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from graph_freshness import current_graph_freshness
from harness_common import EVENTS_PATH, JOBS_PATH, LOCKS_ROOT, all_jobs, latest_event_index, utc_now_iso
from lock_policy import lock_snapshot


QUEUE_STATUS_PATH = JOBS_PATH.parent / "queue-status.json"
TERMINAL_EVENTS = {"job_succeeded", "job_failed"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a queue status summary for the Hermes external harness."
    )
    parser.add_argument(
        "--output",
        default=str(QUEUE_STATUS_PATH),
        help="Output JSON path. Defaults to the active runtime queue status path.",
    )
    return parser.parse_args()


def lock_names(lock_paths: List[Path]) -> List[str]:
    names: List[str] = []
    for path in lock_paths:
        if path.suffix != ".lock":
            continue
        names.append(path.stem)
    return sorted(names)


def build_queue_status(
    jobs: List[Dict[str, Any]],
    latest_events: Dict[str, Dict[str, Any]],
    lock_state: List[Dict[str, Any]],
    *,
    generated_at: str,
) -> Dict[str, Any]:
    active_locks = [str(item["name"]) for item in lock_state]
    stale_locks = [item for item in lock_state if item.get("stale")]
    pending = 0
    active = 0
    failed = 0
    succeeded = 0
    queued = 0
    by_type: Dict[str, Dict[str, int]] = {}
    latest_job_id: str | None = jobs[-1]["job_id"] if jobs else None

    for job in jobs:
        job_type = str(job.get("job_type") or "unknown")
        bucket = by_type.setdefault(
            job_type,
            {"pending": 0, "queued": 0, "active": 0, "failed": 0, "succeeded": 0},
        )

        event = latest_events.get(job["job_id"])
        event_type = event.get("event_type") if event else None

        if event_type == "job_succeeded":
            succeeded += 1
            bucket["succeeded"] += 1
            continue
        if event_type == "job_failed":
            failed += 1
            bucket["failed"] += 1
            continue

        pending += 1
        bucket["pending"] += 1
        if event_type == "job_started":
            active += 1
            bucket["active"] += 1
        else:
            queued += 1
            bucket["queued"] += 1

    return {
        "generated_at": generated_at,
        "jobs_path": str(JOBS_PATH),
        "events_path": str(EVENTS_PATH),
        "counts": {
            "total_jobs": len(jobs),
            "pending": pending,
            "queued": queued,
            "active": active,
            "failed": failed,
            "succeeded": succeeded,
        },
        "active_locks": active_locks,
        "lock_count": len(active_locks),
        "stale_lock_count": len(stale_locks),
        "locks": lock_state,
        "latest_job_id": latest_job_id,
        "job_types": by_type,
        "graph_freshness": current_graph_freshness(),
    }


def current_lock_state(*, stale_lock_age_seconds: float = 900.0) -> List[Dict[str, Any]]:
    return lock_snapshot(lock_root=LOCKS_ROOT, stale_after_seconds=stale_lock_age_seconds)


def write_queue_status(
    output_path: Path = QUEUE_STATUS_PATH,
    *,
    stale_lock_age_seconds: float = 900.0,
) -> Dict[str, Any]:
    payload = build_queue_status(
        all_jobs(),
        latest_event_index(),
        current_lock_state(stale_lock_age_seconds=stale_lock_age_seconds),
        generated_at=utc_now_iso(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    args = parse_args()
    payload = write_queue_status(Path(args.output))
    counts = payload["counts"]
    print(
        "queue_status "
        f"pending={counts['pending']} queued={counts['queued']} active={counts['active']} "
        f"failed={counts['failed']} succeeded={counts['succeeded']} "
        f"locks={payload['lock_count']} stale_locks={payload['stale_lock_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
