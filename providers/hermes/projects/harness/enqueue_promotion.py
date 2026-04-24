from __future__ import annotations

import argparse

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
from promotion_worthiness import evaluate_session_worthiness, resolve_session_json_path
from topic_episode_placement_engine import evaluate_session_placement


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enqueue one promotion job for the single-writer harness."
    )
    parser.add_argument("--profile", help="Hermes profile name")
    parser.add_argument("--session-id", help="Hermes session id")
    parser.add_argument("--session-json", help="Explicit Hermes session JSON path")
    parser.add_argument("--refresh-transcript", action="store_true")
    parser.add_argument(
        "--chain-graph",
        action="store_true",
        help="Enqueue a Graphify rebuild after promotion succeeds",
    )
    parser.add_argument("--force", action="store_true", help="Bypass active duplicate detection")
    parser.add_argument("--requested-by", default="manual")
    parser.add_argument("--parent-question-id", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not any([args.profile, args.session_id, args.session_json]):
        raise SystemExit(
            "At least one of --profile, --session-id, or --session-json is required."
        )

    payload = {
        "profile": args.profile,
        "session_id": args.session_id,
        "session_json": args.session_json,
        "refresh_transcript": args.refresh_transcript,
        "enqueue_graph_rebuild": args.chain_graph,
        "graph_rebuild_payload": {
            "vault": DEFAULT_VAULT,
            "sandbox_root": DEFAULT_GRAPHIFY_SANDBOX,
            "manifest": DEFAULT_GRAPHIFY_MANIFEST,
            "refresh_semantic": False,
            "directed": False,
        },
    }
    profile, session_json_path = resolve_session_json_path(
        profile=args.profile,
        session_id=args.session_id,
        session_json=args.session_json,
    )
    session_id = args.session_id or session_json_path.stem.replace("session_", "")
    verdict = evaluate_session_worthiness(
        session_json_path=session_json_path,
        profile=profile,
        session_id=session_id,
    )
    if not verdict["promote"]:
        record_event(
            "promotion_enqueue_blocked_worthiness",
            {
                "profile": profile,
                "session_id": session_id,
                "requested_by": args.requested_by,
                "score": verdict["score"],
                "reason_labels": verdict["reason_labels"],
            },
        )
        raise SystemExit(
            f"Promotion blocked by worthiness evaluator: score={verdict['score']} labels={','.join(verdict['reason_labels'])}"
        )
    payload["profile"] = profile
    payload["session_id"] = session_id
    payload["session_json"] = str(session_json_path) if args.session_json else args.session_json
    payload["worthiness_verdict"] = verdict
    placement_verdict = evaluate_session_placement(
        session_json_path=session_json_path,
        profile=profile,
        session_id=session_id,
        vault_root=DEFAULT_VAULT,
    )
    if not placement_verdict["place"]:
        record_event(
            "promotion_enqueue_blocked_placement",
            {
                "profile": profile,
                "session_id": session_id,
                "requested_by": args.requested_by,
                "reasons": placement_verdict["reasons"],
            },
        )
        raise SystemExit(
            f"Promotion blocked by placement evaluator: reasons={','.join(placement_verdict['reasons'])}"
        )
    payload["placement_verdict"] = placement_verdict
    with retrying_file_lock("queue"):
        normalized_payload = json_ready(payload)
        existing = active_job_for_key(job_key_for("promotion", normalized_payload))
        if existing and not args.force:
            record_event(
                "job_duplicate_skipped",
                {
                    "job_type": "promotion",
                    "existing_job_id": existing["job_id"],
                    "requested_by": args.requested_by,
                },
            )
            print(f"SKIPPED_DUPLICATE {existing['job_id']}")
            return 0

        job = enqueue_job(
            build_job(
                "promotion",
                payload,
                requested_by=args.requested_by,
                parent_question_id=args.parent_question_id,
            )
        )
    print(job["job_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
