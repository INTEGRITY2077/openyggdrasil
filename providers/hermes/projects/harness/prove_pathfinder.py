from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import deep_search_executor
from harness_common import OPS_ROOT
from map_identity import build_claim_id
from pathfinder import build_pathfinder_bundle
from provenance_store import render_provenance_page


OUTPUT_PATH = OPS_ROOT / "pathfinder-proof.json"


def write_topic_page(path: Path, *, title: str, topic_id: str, page_id: str, episodes: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [
        "---",
        f'title: "{title}"',
        "type: query",
        f"page_id: {page_id}",
        f"topic_id: {topic_id}",
        "---",
        "",
        f"# {title}",
        "",
        "## Episodes",
        "",
    ]
    for episode_id, question, answer in episodes:
        episode_label = episode_id.split(":")[-1]
        chunks.extend(
            [
                f"<!-- episode:{episode_id}:start -->",
                f"## Episode {episode_label}",
                "",
                "### Question",
                "",
                question,
                "",
                "### Answer",
                "",
                answer,
                "",
                f"<!-- episode:{episode_id}:end -->",
                "",
            ]
        )
    path.write_text("\n".join(chunks), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pathfinder-proof-") as tmpdir:
        vault_root = Path(tmpdir) / "vault"
        topic_page_path = vault_root / "queries" / "mailbox-reverse-push.md"
        write_topic_page(
            topic_page_path,
            title="Mailbox Reverse Push",
            topic_id="topic:mailbox-reverse-push",
            page_id="page:queries/mailbox-reverse-push",
            episodes=[
                (
                    "episode:mailbox-reverse-push:2026-04-22",
                    "How should mailbox reverse push work?",
                    "It should stay session-bound.",
                ),
                (
                    "episode:mailbox-reverse-push:2026-04-23",
                    "What changed today?",
                    "Operator lane separation was added.",
                ),
            ],
        )
        provenance_root = vault_root / "_meta" / "provenance"
        provenance_root.mkdir(parents=True, exist_ok=True)
        first_provenance = render_provenance_page(
            existing_text=None,
            placement_verdict={
                "topic_id": "topic:mailbox-reverse-push",
                "episode_id": "episode:mailbox-reverse-push:2026-04-22",
                "page_id": "page:queries/mailbox-reverse-push",
                "topic_title": "Mailbox Reverse Push",
            },
            source_rel="raw/transcripts/2026/2026-04-22-session-1.md",
            question="How should mailbox reverse push work?",
            answer="It should stay session-bound.",
            created="2026-04-22",
        )
        second_provenance = render_provenance_page(
            existing_text=first_provenance,
            placement_verdict={
                "topic_id": "topic:mailbox-reverse-push",
                "episode_id": "episode:mailbox-reverse-push:2026-04-23",
                "page_id": "page:queries/mailbox-reverse-push",
                "topic_title": "Mailbox Reverse Push",
            },
            source_rel="raw/transcripts/2026/2026-04-23-session-2.md",
            question="What changed today?",
            answer="Operator lane separation was added.",
            created="2026-04-23",
            edge_evaluator=lambda **_: {
                "supports": [
                    build_claim_id(
                        topic_id="topic:mailbox-reverse-push",
                        claim_key="episode:mailbox-reverse-push:2026-04-22:summary",
                    )
                ],
                "supersedes": [],
                "contradicts": [],
                "reason_labels": ["supports_prior_claim"],
                "summary": "The newer episode extends the earlier session-bound decision.",
            },
        )
        provenance_path = provenance_root / "mailbox-reverse-push.md"
        provenance_path.write_text(second_provenance, encoding="utf-8")

        same_topic_bundle = build_pathfinder_bundle(
            query_text="How did mailbox reverse push change today?",
            vault_root=vault_root,
        )
        new_topic_bundle = build_pathfinder_bundle(
            query_text="What retention policy should we use for RL checkpoints?",
            vault_root=vault_root,
        )

        original_vault_root = deep_search_executor.VAULT_ROOT
        original_graph_path = deep_search_executor.GRAPH_PATH
        original_run_graphify_query = deep_search_executor.run_graphify_query
        try:
            deep_search_executor.VAULT_ROOT = vault_root
            deep_search_executor.GRAPH_PATH = Path(tmpdir) / "graphify-out" / "graph.json"
            deep_search_executor.run_graphify_query = lambda question: "unused in stale fallback"
            search_result = deep_search_executor.execute_deep_search(
                profile="wiki",
                session_id=f"pathfinder-{uuid.uuid4().hex[:8]}",
                parent_question_id=f"question-{uuid.uuid4().hex[:8]}",
                mailbox_namespace=f"proof-pathfinder-{uuid.uuid4().hex[:8]}",
                question="How did mailbox reverse push change today?",
            )
        finally:
            deep_search_executor.VAULT_ROOT = original_vault_root
            deep_search_executor.GRAPH_PATH = original_graph_path
            deep_search_executor.run_graphify_query = original_run_graphify_query

    payload = {
        "status": "ok",
        "same_topic_bundle": {
            "anchor_type": same_topic_bundle["anchor_type"],
            "anchor_id": same_topic_bundle["anchor_id"],
            "bundle_mode": same_topic_bundle["bundle_mode"],
            "episode_ids": same_topic_bundle["episode_ids"],
            "claim_ids": same_topic_bundle["claim_ids"],
            "source_paths": same_topic_bundle["source_paths"],
            "support_facts": same_topic_bundle["support_facts"],
        },
        "new_topic_bundle": {
            "anchor_type": new_topic_bundle["anchor_type"],
            "anchor_id": new_topic_bundle["anchor_id"],
            "episode_ids": new_topic_bundle["episode_ids"],
        },
        "deep_search_integration": {
            "packet_id": search_result["packet"]["message_id"],
            "graph_query_used": search_result["packet"]["payload"]["graph_freshness"]["graph_query_used"],
            "pathfinder_anchor_id": search_result["pathfinder_bundle"]["anchor_id"],
            "fact_count": len(search_result["packet"]["payload"]["facts"]),
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
