from __future__ import annotations

import argparse
from typing import Any, Dict, Mapping

from harness_common import (
    JOBS_PATH,
    active_job_for_key,
    append_jsonl,
    build_job,
    file_lock,
    job_key_for,
    json_ready,
    queued_jobs,
)
from job_registry import JOB_REGISTRY, JobSpec, resolve_job_spec
from promotion_worthiness import ensure_promotion_job_has_worthiness
from role_registry import ensure_role_can_run_job, ensure_scope_satisfies_write_scope
from subagent_telemetry import record_subagent_event
from topic_episode_placement import ensure_promotion_job_has_placement
from worker_runtime import (
    job_scope,
    record_worker_event,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Hermes external command worker."
    )
    parser.add_argument("--once", action="store_true", help="Process current queue then exit")
    parser.add_argument("--max-jobs", type=int, default=0, help="Optional limit for one run")
    return parser.parse_args()


def enqueue_followup_graph_rebuild(parent_job: Dict[str, Any], graph_payload: Dict[str, Any]) -> None:
    normalized_payload = json_ready(graph_payload)
    existing = active_job_for_key(job_key_for("graph_rebuild", normalized_payload))
    if existing:
        record_worker_event(
            "job_duplicate_skipped",
            {
                "job_id": parent_job["job_id"],
                "job_type": parent_job["job_type"],
                "skipped_job_type": "graph_rebuild",
                "existing_job_id": existing["job_id"],
            },
        )
        return

    chained_job = build_job(
        "graph_rebuild",
        graph_payload,
        requested_by="command-worker",
        parent_question_id=parent_job.get("parent_question_id"),
    )
    chained_job["replayed_from"] = parent_job["job_id"]
    append_jsonl(JOBS_PATH, chained_job)
    record_worker_event(
        "job_enqueued",
        {
            "job_id": chained_job["job_id"],
            "job_type": chained_job["job_type"],
            "parent_job_id": parent_job["job_id"],
        },
    )


def process_job(
    job: Dict[str, Any],
    *,
    registry: Mapping[str, JobSpec] | None = None,
) -> None:
    job_type = job["job_type"]
    spec = resolve_job_spec(job_type, registry=registry)
    role = spec.target_role
    capability = spec.capability
    scope = job_scope(job)
    ensure_role_can_run_job(
        role=role,
        job_type=job_type,
        capability=capability,
        inference_mode=spec.inference_mode,
        write_scope=spec.write_scope,
    )
    ensure_scope_satisfies_write_scope(write_scope=spec.write_scope, scope=scope)
    if job_type == "promotion":
        ensure_promotion_job_has_worthiness(job)
        ensure_promotion_job_has_placement(job)
    record_worker_event(
        "job_started",
        {
            "job_id": job["job_id"],
            "job_type": job_type,
        },
    )
    record_subagent_event(
        trace_id=job["job_id"],
        capability=capability,
        role=role,
        actor=role,
        decider="command-worker",
        action="job_started",
        status="start",
        producer="command-worker",
        parent_question_id=job.get("parent_question_id"),
        artifacts={
            "job_id": job["job_id"],
            "parent_job_id": job.get("replayed_from"),
            "replay_root_job_id": job.get("replay_root_job_id"),
            "replay_depth": job.get("replay_depth"),
        },
        scope=scope,
        inference={"mode": spec.inference_mode},
    )
    try:
        result = spec.handler(job)
        if job_type == "promotion" and result.get("chained_graph_payload"):
            enqueue_followup_graph_rebuild(job, result["chained_graph_payload"])
    except Exception as exc:
        record_worker_event(
            "job_failed",
            {
                "job_id": job["job_id"],
                "job_type": job_type,
                "error": str(exc),
            },
        )
        record_subagent_event(
            trace_id=job["job_id"],
            capability=capability,
            role=role,
            actor=role,
            decider="command-worker",
            action="job_failed",
            status="failure",
            producer="command-worker",
            parent_question_id=job.get("parent_question_id"),
            artifacts={
                "job_id": job["job_id"],
                "parent_job_id": job.get("replayed_from"),
                "replay_root_job_id": job.get("replay_root_job_id"),
                "replay_depth": job.get("replay_depth"),
            },
            scope=scope,
            inference={"mode": spec.inference_mode},
            details={"error": str(exc)},
        )
        raise
    else:
        record_worker_event(
            "job_succeeded",
            {
                "job_id": job["job_id"],
                "job_type": job_type,
            },
        )
        record_subagent_event(
            trace_id=job["job_id"],
            capability=capability,
            role=role,
            actor=role,
            decider="command-worker",
            action="job_succeeded",
            status="success",
            producer="command-worker",
            parent_question_id=job.get("parent_question_id"),
            artifacts={
                "job_id": job["job_id"],
                "parent_job_id": job.get("replayed_from"),
                "replay_root_job_id": job.get("replay_root_job_id"),
                "replay_depth": job.get("replay_depth"),
            },
            scope=scope,
            inference={"mode": spec.inference_mode},
        )


def main() -> int:
    args = parse_args()
    processed = 0

    with file_lock("worker"):
        while True:
            jobs = queued_jobs()
            if not jobs:
                break

            process_job(jobs[0])
            processed += 1

            if args.max_jobs and processed >= args.max_jobs:
                break
            if args.once and not queued_jobs():
                break

    print(f"processed_jobs={processed}")
    return 0
