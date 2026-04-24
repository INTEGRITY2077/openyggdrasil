from __future__ import annotations

import argparse
import json
from pathlib import Path

from command_worker import process_job
from emit_deep_search_command import build_command as build_deep_search_command
from job_registry import JOB_REGISTRY, JobSpec
from observer_emit import build_lint_command
from postman_route_commands_once import route_command


def valid_promotion_verdict() -> dict:
    return {
        "schema_version": "promotion_worthiness.v1",
        "profile": "wiki",
        "session_id": "registry-proof",
        "promote": True,
        "score": 0.82,
        "durability_score": 0.88,
        "novelty_score": 0.73,
        "decision_density_score": 0.84,
        "rederivation_cost_score": 0.77,
        "triviality_score": 0.11,
        "prefilter_ok": True,
        "prefilter_reasons": [],
        "evaluation_mode": "hermes_runtime",
        "reason_labels": ["durable_decision", "hard_to_rederive"],
        "summary": "Contains a durable decision that should be promoted.",
        "evaluated_at": "2026-04-22T00:00:00+00:00",
    }


def valid_placement_verdict() -> dict:
    return {
        "schema_version": "topic_episode_placement.v1",
        "profile": "wiki",
        "session_id": "registry-proof",
        "place": True,
        "topic_id": "topic:registry-proof",
        "episode_id": "episode:registry-proof:2026-04-22",
        "page_id": "page:queries/registry-proof",
        "canonical_relative_path": "queries/registry-proof.md",
        "topic_title": "Registry Proof",
        "placement_mode": "existing_topic_new_episode",
        "page_action": "update_existing_page",
        "claim_actions": ["append_claim"],
        "reasons": ["same durable topic as prior day"],
        "evaluation_mode": "deterministic_test",
        "evaluated_at": "2026-04-22T00:00:00+00:00",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove runtime role/command enforcement blocks invalid flows.")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    blocked: dict[str, str] = {}

    bad_role_command = build_lint_command(profile="wiki", session_id="registry-proof")
    bad_role_command["payload"]["target_role"] = "sot_writer"
    try:
        route_command(bad_role_command)
    except RuntimeError as exc:
        blocked["command_target_role"] = str(exc)
    else:
        raise RuntimeError("command target_role violation was not blocked")

    bad_capability_command = build_deep_search_command(
        profile="wiki",
        session_id="registry-proof",
        question="How does registry enforcement work?",
    )
    bad_capability_command["payload"]["capability"] = "lint"
    try:
        route_command(bad_capability_command)
    except RuntimeError as exc:
        blocked["command_capability"] = str(exc)
    else:
        raise RuntimeError("command capability violation was not blocked")

    invalid_role_spec = JobSpec(
        job_type="promotion",
        capability="ingest",
        target_role="postman",
        inference_mode="deterministic",
        write_scope="vault",
        handler=lambda job: {"stdout": "noop", "chained_graph_payload": None},
    )
    promotion_job = {
        "job_id": "registry-proof-job-role",
        "job_type": "promotion",
        "payload": {
            "profile": "wiki",
            "session_id": "registry-proof",
            "worthiness_verdict": valid_promotion_verdict(),
            "placement_verdict": valid_placement_verdict(),
        },
    }
    try:
        process_job(promotion_job, registry={"promotion": invalid_role_spec})
    except RuntimeError as exc:
        blocked["job_target_role"] = str(exc)
    else:
        raise RuntimeError("job target_role violation was not blocked")

    bad_scope_job = {
        "job_id": "registry-proof-job-scope",
        "job_type": "graph_rebuild",
        "payload": {
            "vault": r"%HERMES_ROOT%\vault",
        },
    }
    try:
        process_job(bad_scope_job, registry=JOB_REGISTRY)
    except RuntimeError as exc:
        blocked["job_write_scope"] = str(exc)
    else:
        raise RuntimeError("job write_scope violation was not blocked")

    result = {
        "status": "ok",
        "blocked": blocked,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    args = parse_args()
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
