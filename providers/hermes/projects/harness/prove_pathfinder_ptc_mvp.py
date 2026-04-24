from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness_common import OPS_ROOT
from map_identity import build_claim_id
from pathfinder_ptc_mvp import PathfinderPTCMVPRuntime
from provenance_store import render_provenance_page


OUTPUT_PATH = OPS_ROOT / "pathfinder-ptc-mvp-proof.json"


def write_topic_page(path: Path, *, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'title: "{title}"\n'
        "type: query\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Episodes\n\n"
        "<!-- episode:episode:mailbox-reverse-push:2026-04-22:start -->\n"
        "## Episode 2026-04-22\n\n"
        "### Question\n\nHow does mailbox reverse push work?\n\n"
        "### Answer\n\nIt should stay session-bound.\n\n"
        "<!-- episode:episode:mailbox-reverse-push:2026-04-22:end -->\n\n"
        "<!-- episode:episode:mailbox-reverse-push:2026-04-23:start -->\n"
        "## Episode 2026-04-23\n\n"
        "### Question\n\nWhat changed today?\n\n"
        "### Answer\n\nOperator lane separation was added.\n\n"
        "<!-- episode:episode:mailbox-reverse-push:2026-04-23:end -->\n",
        encoding="utf-8",
    )


def make_verdict(*, episode_id: str, session_id: str) -> dict:
    return {
        "schema_version": "topic_episode_placement.v1",
        "profile": "wiki",
        "session_id": session_id,
        "place": True,
        "topic_id": "topic:mailbox-reverse-push",
        "episode_id": episode_id,
        "page_id": "page:queries/mailbox-reverse-push",
        "canonical_relative_path": "queries/mailbox-reverse-push.md",
        "topic_title": "Mailbox Reverse Push",
        "placement_mode": "existing_topic_new_episode",
        "page_action": "update_existing_page",
        "claim_actions": ["append_claim"],
        "reasons": ["same durable topic as prior day"],
        "evaluation_mode": "deterministic_test",
        "evaluated_at": "2026-04-23T00:00:00+00:00",
    }


def fake_anchor(*, query_text: str, existing_topics: list[dict[str, str]]) -> dict[str, object]:
    if "mailbox reverse push" in query_text.lower():
        return {
            "topic_key": "mailbox-reverse-push",
            "reason_labels": ["same_topic_revisit"],
            "summary": "This question revisits the mailbox reverse push topic.",
        }
    return {
        "topic_key": None,
        "reason_labels": ["new_topic"],
        "summary": "No stable topic anchor exists yet.",
    }


def seed(vault_root: Path) -> None:
    prior_claim_id = build_claim_id(
        topic_id="topic:mailbox-reverse-push",
        claim_key="episode:mailbox-reverse-push:2026-04-22:summary",
    )
    write_topic_page(vault_root / "queries" / "mailbox-reverse-push.md", title="Mailbox Reverse Push")
    provenance_root = vault_root / "_meta" / "provenance"
    provenance_root.mkdir(parents=True, exist_ok=True)
    first = render_provenance_page(
        existing_text=None,
        placement_verdict=make_verdict(
            episode_id="episode:mailbox-reverse-push:2026-04-22",
            session_id="session-1",
        ),
        source_rel="raw/transcripts/2026/2026-04-22-session-1.md",
        question="How should mailbox reverse push work?",
        answer="It should stay session-bound.",
        created="2026-04-22",
    )
    second = render_provenance_page(
        existing_text=first,
        placement_verdict=make_verdict(
            episode_id="episode:mailbox-reverse-push:2026-04-23",
            session_id="session-2",
        ),
        source_rel="raw/transcripts/2026/2026-04-23-session-2.md",
        question="What changed today?",
        answer="Operator lane separation was added.",
        created="2026-04-23",
        edge_evaluator=lambda **_: {
            "supports": [prior_claim_id],
            "supersedes": [],
            "contradicts": [],
            "reason_labels": ["supports_prior_claim"],
            "summary": "The newer episode extends the earlier session-bound decision.",
        },
    )
    (provenance_root / "mailbox-reverse-push.md").write_text(second, encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pathfinder-ptc-mvp-") as tmpdir:
        base = Path(tmpdir)
        vault_root = base / "vault"
        seed(vault_root)
        runtime = PathfinderPTCMVPRuntime(
            vault_root=vault_root,
            scratch_root=base / "scratch",
            anchor_evaluator=fake_anchor,
        )
        same_topic = runtime.execute(query_text="How did mailbox reverse push change today?")
        new_topic = runtime.execute(query_text="What retention policy should we use for RL checkpoints?")

    payload = {
        "status": "ok",
        "runtime_mode": same_topic["runtime"]["runtime_mode"],
        "same_topic_bundle": {
            "anchor_id": same_topic["bundle"]["anchor_id"],
            "bundle_mode": same_topic["bundle"]["bundle_mode"],
            "support_facts": same_topic["bundle"]["support_facts"],
            "tool_calls": [row["tool"] for row in same_topic["tool_calls"]],
        },
        "new_topic_bundle": {
            "anchor_type": new_topic["bundle"]["anchor_type"],
            "bundle_mode": new_topic["bundle"]["bundle_mode"],
            "tool_calls": [row["tool"] for row in new_topic["tool_calls"]],
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
