from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from topic_episode_placement_engine import evaluate_session_placement


@dataclass(frozen=True)
class PlacementReplayCase:
    name: str
    session_id: str
    session_start: str
    user_text: str
    assistant_text: str
    existing_topics: list[dict[str, str]] = field(default_factory=list)
    expected_topic_relation: str = "reuse_existing_topic"
    expected_existing_topic_key: str | None = None
    expected_placement_mode: str | None = None
    preseed_episode_marker: bool = False
    profile: str = "wiki"


def topic_key_from_canonical_relative_path(canonical_relative_path: str) -> str:
    normalized = canonical_relative_path.replace("\\", "/").strip().removeprefix("queries/")
    if normalized.endswith(".md"):
        normalized = normalized[:-3]
    return normalized


def write_session_json(root: Path, case: PlacementReplayCase) -> Path:
    session_json_path = root / f"{case.session_id}.json"
    payload = {
        "session_id": case.session_id,
        "session_start": case.session_start,
        "messages": [
            {"role": "user", "content": case.user_text},
            {"role": "assistant", "content": case.assistant_text},
        ],
    }
    session_json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return session_json_path


def _topic_title_from_key(topic_key: str) -> str:
    return " ".join(part.capitalize() for part in topic_key.replace("/", " ").replace("_", " ").split("-"))


def prepare_existing_topics(vault_root: Path, case: PlacementReplayCase) -> None:
    queries_root = vault_root / "queries"
    queries_root.mkdir(parents=True, exist_ok=True)
    for topic in case.existing_topics:
        topic_key = topic["topic_key"]
        relative_path = topic.get("canonical_relative_path") or f"queries/{topic_key}.md"
        page_path = vault_root / relative_path
        page_path.parent.mkdir(parents=True, exist_ok=True)
        title = topic.get("topic_title") or _topic_title_from_key(topic_key)
        content = (
            "---\n"
            f'title: "{title}"\n'
            "type: query\n"
            "---\n\n"
            f"# {title}\n\n"
            "## Episodes\n"
        )
        if case.preseed_episode_marker and topic_key == case.expected_existing_topic_key:
            date_key = case.session_start[:10]
            content += (
                f"\n<!-- episode:episode:{topic_key}:{date_key}:start -->\n"
                f"### Episode {date_key}\n"
                "- Pre-seeded episode block.\n"
                f"<!-- episode:episode:{topic_key}:{date_key}:end -->\n"
            )
        page_path.write_text(content, encoding="utf-8")


def evaluate_case_result(case: PlacementReplayCase, verdict: dict[str, Any]) -> dict[str, Any]:
    actual_topic_key = topic_key_from_canonical_relative_path(verdict["canonical_relative_path"])
    expected_episode_suffix = case.session_start[:10]
    topic_relation_passed = False
    if case.expected_topic_relation == "reuse_existing_topic":
        topic_relation_passed = actual_topic_key == (case.expected_existing_topic_key or "")
    elif case.expected_topic_relation == "new_topic":
        topic_relation_passed = actual_topic_key != (case.expected_existing_topic_key or "")
    else:
        raise RuntimeError(f"Unsupported expected_topic_relation: {case.expected_topic_relation}")

    episode_date_passed = verdict["episode_id"].endswith(expected_episode_suffix)
    placement_mode_passed = True
    if case.expected_placement_mode:
        placement_mode_passed = verdict["placement_mode"] == case.expected_placement_mode

    overall_passed = topic_relation_passed and episode_date_passed and placement_mode_passed
    return {
        "name": case.name,
        "expected_topic_relation": case.expected_topic_relation,
        "expected_existing_topic_key": case.expected_existing_topic_key,
        "expected_placement_mode": case.expected_placement_mode,
        "actual_topic_key": actual_topic_key,
        "actual_placement_mode": verdict["placement_mode"],
        "episode_id": verdict["episode_id"],
        "topic_relation_passed": topic_relation_passed,
        "episode_date_passed": episode_date_passed,
        "placement_mode_passed": placement_mode_passed,
        "overall_passed": overall_passed,
    }


def summarize_case_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = len(results)
    passed_cases = sum(1 for item in results if item["overall_passed"])
    failed_cases = total_cases - passed_cases
    accuracy = round(passed_cases / total_cases, 4) if total_cases else 0.0
    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "accuracy": accuracy,
        "failed_case_names": [item["name"] for item in results if not item["overall_passed"]],
    }


def build_replay_cases() -> list[PlacementReplayCase]:
    return [
        PlacementReplayCase(
            name="same_topic_revisit_new_day",
            session_id="session-same-topic-1",
            session_start="2026-04-23T09:00:00+00:00",
            user_text="Yesterday we worked on mailbox reverse push. Today I need the mailbox reverse push design updated for the new session-bound inbox rule.",
            assistant_text="This continues the same durable mailbox reverse push topic and adds a new day's decision about session-bound delivery.",
            existing_topics=[
                {
                    "topic_key": "mailbox-reverse-push",
                    "topic_title": "Mailbox Reverse Push",
                }
            ],
            expected_topic_relation="reuse_existing_topic",
            expected_existing_topic_key="mailbox-reverse-push",
            expected_placement_mode="existing_topic_new_episode",
        ),
        PlacementReplayCase(
            name="same_topic_same_day_refresh",
            session_id="session-same-topic-2",
            session_start="2026-04-23T13:30:00+00:00",
            user_text="We are still refining mailbox reverse push today. Keep the same topic but refresh the same day's episode with the new operator lane rule.",
            assistant_text="This is still the same mailbox reverse push topic and same day episode, with one more operator-lane refinement.",
            existing_topics=[
                {
                    "topic_key": "mailbox-reverse-push",
                    "topic_title": "Mailbox Reverse Push",
                }
            ],
            expected_topic_relation="reuse_existing_topic",
            expected_existing_topic_key="mailbox-reverse-push",
            expected_placement_mode="existing_topic_existing_episode",
            preseed_episode_marker=True,
        ),
        PlacementReplayCase(
            name="wording_variant_same_topic",
            session_id="session-wording-variant-1",
            session_start="2026-04-23T15:00:00+00:00",
            user_text="Should the external harness stay outside Hermes core, or do we collapse the mailbox orchestration into the core runtime?",
            assistant_text="The durable subject is still the external harness boundary and it should remain outside Hermes core.",
            existing_topics=[
                {
                    "topic_key": "external-harness-boundary",
                    "topic_title": "External Harness Boundary",
                }
            ],
            expected_topic_relation="reuse_existing_topic",
            expected_existing_topic_key="external-harness-boundary",
            expected_placement_mode="existing_topic_new_episode",
        ),
        PlacementReplayCase(
            name="clear_topic_switch_new_topic",
            session_id="session-topic-switch-1",
            session_start="2026-04-23T17:00:00+00:00",
            user_text="What retention policy should we use for RL training checkpoints across long-running experiments?",
            assistant_text="Use bounded retention with recent checkpoints kept hot and older checkpoints compacted or pruned.",
            existing_topics=[
                {
                    "topic_key": "mailbox-reverse-push",
                    "topic_title": "Mailbox Reverse Push",
                }
            ],
            expected_topic_relation="new_topic",
            expected_existing_topic_key="mailbox-reverse-push",
        ),
    ]


def run_replay_case(
    *,
    root: Path,
    case: PlacementReplayCase,
) -> dict[str, Any]:
    case_root = root / case.name
    case_root.mkdir(parents=True, exist_ok=True)
    vault_root = case_root / "vault"
    prepare_existing_topics(vault_root, case)
    session_json_path = write_session_json(case_root, case)
    verdict = evaluate_session_placement(
        session_json_path=session_json_path,
        profile=case.profile,
        session_id=case.session_id,
        vault_root=vault_root,
    )
    result = evaluate_case_result(case, verdict)
    return {
        "case": asdict(case),
        "verdict": verdict,
        "result": result,
    }
