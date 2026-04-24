from __future__ import annotations

import argparse
from pathlib import Path

from harness_common import (
    active_job_for_key,
    DEFAULT_GRAPHIFY_MANIFEST,
    DEFAULT_GRAPHIFY_SANDBOX,
    DEFAULT_VAULT,
    build_job,
    enqueue_job,
    job_key_for,
    json_ready,
    record_event,
    retrying_file_lock,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enqueue one Graphify rebuild job for the single-writer harness."
    )
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--sandbox-root", default=str(DEFAULT_GRAPHIFY_SANDBOX))
    parser.add_argument("--manifest", default=str(DEFAULT_GRAPHIFY_MANIFEST))
    parser.add_argument("--refresh-semantic", action="store_true")
    parser.add_argument("--directed", action="store_true")
    parser.add_argument("--force", action="store_true", help="Bypass active duplicate detection")
    parser.add_argument("--requested-by", default="manual")
    parser.add_argument("--parent-question-id", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "vault": Path(args.vault),
        "sandbox_root": Path(args.sandbox_root),
        "manifest": Path(args.manifest),
        "refresh_semantic": args.refresh_semantic,
        "directed": args.directed,
    }
    with retrying_file_lock("queue"):
        normalized_payload = json_ready(payload)
        existing = active_job_for_key(job_key_for("graph_rebuild", normalized_payload))
        if existing and not args.force:
            record_event(
                "job_duplicate_skipped",
                {
                    "job_type": "graph_rebuild",
                    "existing_job_id": existing["job_id"],
                    "requested_by": args.requested_by,
                },
            )
            print(f"SKIPPED_DUPLICATE {existing['job_id']}")
            return 0

        job = enqueue_job(
            build_job(
                "graph_rebuild",
                payload,
                requested_by=args.requested_by,
                parent_question_id=args.parent_question_id,
            )
        )
    print(job["job_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
