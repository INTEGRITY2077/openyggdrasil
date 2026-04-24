from __future__ import annotations

import argparse

from harness_common import (
    build_job,
    enqueue_job,
    failed_jobs,
    find_job,
    record_event,
    retrying_file_lock,
)
from replay_policy import DEFAULT_MAX_REPLAY_DEPTH, apply_replay_lineage, ensure_job_replayable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay one previously failed harness job by re-enqueuing its payload."
    )
    parser.add_argument("--job-id", help="Failed job id to replay")
    parser.add_argument(
        "--latest-failed",
        action="store_true",
        help="Replay the most recent failed job if --job-id is not given",
    )
    parser.add_argument("--requested-by", default="manual-replay")
    parser.add_argument(
        "--max-replay-depth",
        type=int,
        default=DEFAULT_MAX_REPLAY_DEPTH,
        help="Maximum allowed replay depth for one lineage",
    )
    return parser.parse_args()


def choose_failed_job(args: argparse.Namespace) -> dict:
    if args.job_id:
        job = find_job(args.job_id)
        if not job:
            raise SystemExit(f"Failed job not found: {args.job_id}")
        return job

    if args.latest_failed:
        failures = failed_jobs()
        if not failures:
            raise SystemExit("No failed jobs available to replay.")
        return failures[-1]["job"]

    raise SystemExit("Use --job-id or --latest-failed.")


def main() -> int:
    args = parse_args()
    failed_job = choose_failed_job(args)
    try:
        lineage = ensure_job_replayable(failed_job, max_replay_depth=args.max_replay_depth)
    except RuntimeError as exc:
        with retrying_file_lock("queue"):
            record_event(
                "job_replay_blocked",
                {
                    "job_id": failed_job.get("job_id"),
                    "job_type": failed_job.get("job_type"),
                    "parent_question_id": failed_job.get("parent_question_id"),
                    "requested_by": args.requested_by,
                    "max_replay_depth": args.max_replay_depth,
                    "reason": str(exc),
                },
            )
        raise

    with retrying_file_lock("queue"):
        replay_job = build_job(
            failed_job["job_type"],
            failed_job["payload"],
            requested_by=args.requested_by,
            parent_question_id=lineage.parent_question_id,
        )
        apply_replay_lineage(replay_job, source_job=failed_job, lineage=lineage)
        enqueue_job(replay_job)
        record_event(
            "job_replayed",
            {
                "job_id": replay_job["job_id"],
                "replayed_from": failed_job["job_id"],
                "replay_root_job_id": replay_job["replay_root_job_id"],
                "replay_depth": replay_job["replay_depth"],
                "job_type": replay_job["job_type"],
                "parent_question_id": replay_job.get("parent_question_id"),
            },
        )
    print(replay_job["job_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
