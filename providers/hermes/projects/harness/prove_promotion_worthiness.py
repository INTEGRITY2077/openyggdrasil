from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import command_worker
from command_worker import process_job
from job_registry import JobSpec
from promotion_worthiness import evaluate_session_worthiness
from topic_episode_placement_engine import evaluate_session_placement


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove Karpathy-style promotion worthiness evaluation and worker enforcement."
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def write_session(path: Path, *, session_id: str, user_text: str, assistant_text: str) -> Path:
    payload = {
        "session_id": session_id,
        "messages": [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def noop_promotion_handler(job: dict) -> dict:
    return {"stdout": "noop", "chained_graph_payload": None}


def fake_map_maker(*, context: dict, existing_topics: list[dict]) -> dict:
    return {
        "topic_key": "external-harness-boundary",
        "topic_title": "External Harness Boundary",
        "reason_labels": ["durable_topic"],
        "summary": "Same durable architectural boundary topic.",
    }


def main() -> int:
    args = parse_args()
    with tempfile.TemporaryDirectory(prefix="promotion-worthiness-proof-") as tmpdir:
        tmp_root = Path(tmpdir)
        worthy_session_path = write_session(
            tmp_root / "session_worthy.json",
            session_id="worthy-session",
            user_text=(
                "Which architectural boundary should own transcript promotion and Graphify rebuild, "
                "and why is that a durable decision for the Hermes stack?"
            ),
            assistant_text=(
                "The external harness should own transcript promotion and Graphify rebuild because "
                "those workflows need serialized writes, publication policy, and replayable orchestration "
                "outside Hermes core. That boundary is durable because it preserves a smaller runtime, keeps "
                "knowledge mutation in one place, and makes the long-term SOT pipeline cheaper to evolve."
            ),
        )
        trivial_session_path = write_session(
            tmp_root / "session_trivial.json",
            session_id="trivial-session",
            user_text="say",
            assistant_text="hello",
        )

        trivial_verdict = evaluate_session_worthiness(
            session_json_path=trivial_session_path,
            profile="wiki",
            session_id="trivial-session",
        )
        worthy_verdict = evaluate_session_worthiness(
            session_json_path=worthy_session_path,
            profile="wiki",
            session_id="worthy-session",
        )
        worthy_placement = evaluate_session_placement(
            session_json_path=worthy_session_path,
            profile="wiki",
            session_id="worthy-session",
            vault_root=tmp_root / "vault",
            evaluator=fake_map_maker,
        )

        if trivial_verdict["promote"]:
            raise RuntimeError("trivial session should not pass the worthiness gate")
        if not worthy_verdict["promote"]:
            raise RuntimeError("worthy session did not pass the worthiness gate")

        valid_job = {
            "job_id": "promotion-worthiness-proof-ok",
            "parent_question_id": "question-promotion-worthiness-proof",
            "job_type": "promotion",
            "payload": {
                "profile": "wiki",
                "session_id": "worthy-session",
                "worthiness_verdict": worthy_verdict,
                "placement_verdict": worthy_placement,
            },
        }
        invalid_job = {
            "job_id": "promotion-worthiness-proof-missing",
            "parent_question_id": "question-promotion-worthiness-proof",
            "job_type": "promotion",
            "payload": {
                "profile": "wiki",
                "session_id": "worthy-session",
            },
        }

        original_record_worker_event = command_worker.record_worker_event
        original_record_subagent_event = command_worker.record_subagent_event
        try:
            command_worker.record_worker_event = lambda *args, **kwargs: None
            command_worker.record_subagent_event = lambda **kwargs: None
            process_job(
                valid_job,
                registry={
                    "promotion": JobSpec(
                        job_type="promotion",
                        capability="ingest",
                        target_role="sot_writer",
                        inference_mode="deterministic",
                        write_scope="vault",
                        handler=noop_promotion_handler,
                    )
                },
            )
            missing_verdict_error: str | None = None
            try:
                process_job(
                    invalid_job,
                    registry={
                        "promotion": JobSpec(
                            job_type="promotion",
                            capability="ingest",
                            target_role="sot_writer",
                            inference_mode="deterministic",
                            write_scope="vault",
                            handler=noop_promotion_handler,
                        )
                    },
                )
            except RuntimeError as exc:
                missing_verdict_error = str(exc)
        finally:
            command_worker.record_worker_event = original_record_worker_event
            command_worker.record_subagent_event = original_record_subagent_event

        if missing_verdict_error is None:
            raise RuntimeError("promotion worker enforcement did not block a missing worthiness verdict")

        result = {
            "status": "ok",
            "trivial_session": {
                "promote": trivial_verdict["promote"],
                "evaluation_mode": trivial_verdict["evaluation_mode"],
                "prefilter_reasons": trivial_verdict["prefilter_reasons"],
            },
            "worthy_session": {
                "promote": worthy_verdict["promote"],
                "evaluation_mode": worthy_verdict["evaluation_mode"],
                "score": worthy_verdict["score"],
                "reason_labels": worthy_verdict["reason_labels"],
                "summary": worthy_verdict["summary"],
            },
            "worker_enforcement": {
                "valid_promotion_job_passed": True,
                "missing_verdict_blocked": True,
                "missing_verdict_error": missing_verdict_error,
            },
            "placement": {
                "topic_id": worthy_placement["topic_id"],
                "episode_id": worthy_placement["episode_id"],
                "canonical_relative_path": worthy_placement["canonical_relative_path"],
            },
        }
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
