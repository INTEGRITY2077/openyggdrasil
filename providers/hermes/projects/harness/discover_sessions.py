from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List

from harness_common import (
    DEFAULT_GRAPHIFY_MANIFEST,
    DEFAULT_GRAPHIFY_SANDBOX,
    DEFAULT_VAULT,
    HERMES_HOME_WIN,
    active_job_for_key,
    build_job,
    enqueue_job,
    job_key_for,
    json_ready,
    record_event,
    retrying_file_lock,
)
from promotion_worthiness import (
    DEFAULT_MIN_ASSISTANT_CHARS,
    evaluate_session_worthiness,
    quality_summary as prefilter_quality_summary,
)
from topic_episode_placement_engine import evaluate_session_placement


RAW_TRANSCRIPTS = DEFAULT_VAULT / "raw" / "transcripts"
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover unpromoted official Hermes sessions and enqueue promotion jobs."
    )
    parser.add_argument(
        "--profiles",
        nargs="*",
        default=None,
        help="Profiles to scan. Defaults to all available profiles plus default.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum sessions to enqueue")
    parser.add_argument("--chain-graph", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--requested-by", default="discovery")
    parser.add_argument(
        "--min-assistant-chars",
        type=int,
        default=DEFAULT_MIN_ASSISTANT_CHARS,
        help="Minimum length for the final assistant answer to qualify for discovery.",
    )
    return parser.parse_args()


def profile_home(profile: str) -> Path:
    if profile == "default":
        return HERMES_HOME_WIN
    return HERMES_HOME_WIN / "profiles" / profile


def available_profiles(explicit_profiles: List[str] | None) -> List[str]:
    if explicit_profiles:
        return explicit_profiles
    profiles = ["default"]
    profiles_root = HERMES_HOME_WIN / "profiles"
    if profiles_root.exists():
        profiles.extend(
            sorted(
                entry.name
                for entry in profiles_root.iterdir()
                if entry.is_dir()
            )
        )
    return profiles


def session_dir(profile: str) -> Path:
    return profile_home(profile) / "sessions"


def transcript_exists_for_session(session_id: str) -> bool:
    return any(RAW_TRANSCRIPTS.glob(f"*/*{session_id}.md"))


def quality_summary(path: Path, *, min_assistant_chars: int) -> dict:
    return prefilter_quality_summary(path, min_assistant_chars=min_assistant_chars)


def session_candidates(profiles: Iterable[str]) -> List[dict]:
    candidates: List[dict] = []
    for profile in profiles:
        directory = session_dir(profile)
        if not directory.exists():
            continue
        for path in directory.glob("session_*.json"):
            session_id = path.stem.replace("session_", "")
            candidates.append(
                {
                    "profile": profile,
                    "session_id": session_id,
                    "session_json": path,
                    "mtime": path.stat().st_mtime,
                }
            )
    candidates.sort(key=lambda item: item["mtime"], reverse=True)
    return candidates


def promotion_payload(candidate: dict, *, chain_graph: bool) -> dict:
    return {
        "profile": candidate["profile"],
        "session_id": candidate["session_id"],
        "session_json": None,
        "refresh_transcript": False,
        "enqueue_graph_rebuild": chain_graph,
        "graph_rebuild_payload": {
            "vault": DEFAULT_VAULT,
            "sandbox_root": DEFAULT_GRAPHIFY_SANDBOX,
            "manifest": DEFAULT_GRAPHIFY_MANIFEST,
            "refresh_semantic": False,
            "directed": False,
        },
    }


def main() -> int:
    args = parse_args()
    profiles = available_profiles(args.profiles)
    scanned = 0
    enqueued = 0
    skipped_promoted = 0
    skipped_active = 0
    skipped_quality = 0
    skipped_worthiness = 0
    skipped_placement = 0

    for candidate in session_candidates(profiles):
        scanned += 1
        session_id = candidate["session_id"]
        if transcript_exists_for_session(session_id):
            skipped_promoted += 1
            continue

        quality = quality_summary(candidate["session_json"], min_assistant_chars=args.min_assistant_chars)
        if not quality["ok"]:
            skipped_quality += 1
            record_event(
                "session_discovery_skipped_quality",
                {
                    "session_id": session_id,
                    "profile": candidate["profile"],
                    "topic": quality["topic"],
                    "assistant_chars": quality["assistant_chars"],
                    "reasons": quality["reasons"],
                },
            )
            continue

        verdict = evaluate_session_worthiness(
            session_json_path=candidate["session_json"],
            profile=candidate["profile"],
            session_id=session_id,
            min_assistant_chars=args.min_assistant_chars,
        )
        if not verdict["promote"]:
            skipped_worthiness += 1
            record_event(
                "session_discovery_skipped_worthiness",
                {
                    "session_id": session_id,
                    "profile": candidate["profile"],
                    "score": verdict["score"],
                    "reason_labels": verdict["reason_labels"],
                    "summary": verdict["summary"],
                },
            )
            continue

        placement_verdict = evaluate_session_placement(
            session_json_path=candidate["session_json"],
            profile=candidate["profile"],
            session_id=session_id,
            vault_root=DEFAULT_VAULT,
        )
        if not placement_verdict["place"]:
            skipped_placement += 1
            record_event(
                "session_discovery_skipped_placement",
                {
                    "session_id": session_id,
                    "profile": candidate["profile"],
                    "reasons": placement_verdict["reasons"],
                },
            )
            continue

        payload = promotion_payload(candidate, chain_graph=args.chain_graph)
        payload["worthiness_verdict"] = verdict
        payload["placement_verdict"] = placement_verdict
        normalized_payload = json_ready(payload)
        key = job_key_for("promotion", normalized_payload)

        with retrying_file_lock("queue"):
            if transcript_exists_for_session(session_id):
                skipped_promoted += 1
                continue

            existing = active_job_for_key(key)
            if existing:
                skipped_active += 1
                record_event(
                    "session_discovery_skipped_active",
                    {
                        "session_id": session_id,
                        "profile": candidate["profile"],
                        "existing_job_id": existing["job_id"],
                    },
                )
                continue

            if args.dry_run:
                record_event(
                    "session_discovery_candidate",
                    {
                    "session_id": session_id,
                    "profile": candidate["profile"],
                        "dry_run": True,
                        "topic": quality["topic"],
                        "assistant_chars": quality["assistant_chars"],
                        "worthiness_score": verdict["score"],
                        "worthiness_labels": verdict["reason_labels"],
                        "topic_id": placement_verdict["topic_id"],
                        "episode_id": placement_verdict["episode_id"],
                     },
                 )
                enqueued += 1
            else:
                job = enqueue_job(
                    build_job("promotion", payload, requested_by=args.requested_by)
                )
                record_event(
                    "session_discovered",
                    {
                        "session_id": session_id,
                        "profile": candidate["profile"],
                        "job_id": job["job_id"],
                        "topic": quality["topic"],
                        "assistant_chars": quality["assistant_chars"],
                        "worthiness_score": verdict["score"],
                        "worthiness_labels": verdict["reason_labels"],
                        "topic_id": placement_verdict["topic_id"],
                        "episode_id": placement_verdict["episode_id"],
                     },
                 )
                enqueued += 1

        if args.limit and enqueued >= args.limit:
            break

    print(
        f"scanned={scanned} enqueued={enqueued} "
        f"skipped_promoted={skipped_promoted} skipped_active={skipped_active} "
        f"skipped_quality={skipped_quality} skipped_worthiness={skipped_worthiness} "
        f"skipped_placement={skipped_placement}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
