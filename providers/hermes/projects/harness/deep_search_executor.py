from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import List

from graph_freshness import current_graph_freshness
from harness_common import DEFAULT_GRAPHIFY_SANDBOX, DEFAULT_VAULT, OPENYGGDRASIL_ROOT
from packet_factory import build_graph_hint_packet
from pathfinder import build_pathfinder_bundle
from plugin_logger import record_plugin_event
from postman_gateway import submit_packet


QUERY_WRAPPER = Path(
    os.getenv(
        "GRAPHIFY_QUERY_WRAPPER",
        str(
            OPENYGGDRASIL_ROOT
            / "providers"
            / "hermes"
            / "projects"
            / "graphify-poc"
            / "query_graphify.py"
        ),
    )
)
SANDBOX_ROOT = DEFAULT_GRAPHIFY_SANDBOX
GRAPH_PATH = Path(
    os.getenv("GRAPHIFY_GRAPH_PATH", str(SANDBOX_ROOT / "graphify-out" / "graph.json"))
)
VAULT_ROOT = DEFAULT_VAULT
WSL_DISTRO = "ubuntu-agent"


def windows_to_wsl(path_value: str | Path) -> str:
    normalized = str(path_value).replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0].lower()
        tail = normalized[2:]
        if tail.startswith("/"):
            tail = tail[1:]
        return f"/mnt/{drive}/{tail}"
    return normalized


def search_candidate_sources(question: str, *, vault_root: Path | None = None) -> List[str]:
    active_vault_root = vault_root or VAULT_ROOT
    tokens = [token.lower() for token in question.replace("?", " ").split() if len(token) >= 4]
    candidates: List[str] = []
    for path in sorted(active_vault_root.rglob("*.md")):
        lowered = path.as_posix().lower()
        if any(token in lowered for token in tokens):
            candidates.append(str(path.resolve()))
        if len(candidates) >= 5:
            break
    if not candidates:
        candidates.append(str((active_vault_root / "index.md").resolve()))
    return candidates


def fallback_note_facts(source_paths: List[str]) -> List[str]:
    facts: List[str] = []
    for raw_path in source_paths[:3]:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = next((line.lstrip("# ").strip() for line in lines if line.startswith("#")), path.stem)
        body = next((line for line in lines if not line.startswith("#") and not line.startswith("---")), "")
        if body:
            facts.append(f"{title}: {body[:180]}")
        else:
            facts.append(title)
    if not facts:
        facts.append("Graphify is stale, so the query path is falling back to linked SOT notes.")
    return facts[:5]


def run_graphify_query(question: str) -> str:
    wrapper_wsl = windows_to_wsl(QUERY_WRAPPER)
    graph_wsl = windows_to_wsl(GRAPH_PATH)
    sandbox_wsl = windows_to_wsl(SANDBOX_ROOT)
    completed = subprocess.run(
        [
            "wsl",
            "-d",
            WSL_DISTRO,
            "bash",
            "-lc",
            f"cd '{sandbox_wsl}' && ./.venv-wsl/bin/python '{wrapper_wsl}' --graph '{graph_wsl}' query {json.dumps(question)}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Graphify query failed")
    return completed.stdout.strip()


def compact_facts(query_output: str) -> List[str]:
    lines = [line.strip() for line in query_output.splitlines() if line.strip()]
    return lines[:5] if lines else ["No graph result lines returned."]


def execute_deep_search(
    *,
    profile: str,
    session_id: str | None,
    question: str,
    parent_question_id: str | None = None,
    mailbox_namespace: str | None = None,
) -> dict:
    freshness = current_graph_freshness(vault_root=VAULT_ROOT, summary_path=GRAPH_PATH.parent / "summary.json")
    pathfinder_bundle = build_pathfinder_bundle(query_text=question, vault_root=VAULT_ROOT)
    record_plugin_event(
        event_type="pathfinder_bundle_built",
        actor="pathfinder",
        parent_question_id=parent_question_id,
        profile=profile,
        session_id=session_id,
        query_text=question,
        artifacts={
            "anchor_id": pathfinder_bundle.get("anchor_id"),
            "topic_id": pathfinder_bundle.get("topic_id"),
            "page_ids": pathfinder_bundle.get("page_ids", []),
            "mailbox_namespace": mailbox_namespace,
        },
        state={
            "anchor_type": pathfinder_bundle.get("anchor_type"),
            "episode_count": len(pathfinder_bundle.get("episode_ids", [])),
            "support_fact_count": len(pathfinder_bundle.get("support_facts", [])),
            "bundle_mode": pathfinder_bundle.get("bundle_mode"),
        },
    )
    source_paths = list(pathfinder_bundle.get("source_paths", [])) or search_candidate_sources(question)
    graph_query_used = freshness["graph_is_trusted"]
    if graph_query_used:
        query_output = run_graphify_query(question)
        facts = compact_facts(query_output)
        human_summary = "Background deep search completed and produced a Graphify-backed hint packet."
        relevance_score = 0.92
        confidence_score = 0.88
    else:
        query_output = ""
        facts = list(pathfinder_bundle.get("support_facts", [])) or fallback_note_facts(source_paths)
        human_summary = "Graphify freshness is not trusted, so the query path fell back to linked SOT notes."
        relevance_score = 0.78
        confidence_score = 0.72
    packet = build_graph_hint_packet(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        topic=question,
        source_paths=source_paths,
        facts=facts,
        human_summary=human_summary,
        relevance_score=relevance_score,
        confidence_score=confidence_score,
        query_text=question,
        producer="deep-search-executor",
    )
    packet["payload"]["graph_freshness"] = {
        "status": freshness["status"],
        "reasons": freshness["reasons"],
        "graph_query_used": graph_query_used,
    }
    packet["payload"]["pathfinder_bundle"] = pathfinder_bundle
    submit_packet(packet, namespace=mailbox_namespace)
    record_plugin_event(
        event_type="graph_hint_generated",
        actor="deep_search_executor",
        parent_question_id=parent_question_id,
        profile=profile,
        session_id=session_id,
        query_text=question,
        artifacts={
            "packet_id": packet["message_id"],
            "packet_type": packet["message_type"],
            "source_paths": packet.get("payload", {}).get("source_paths", []),
            "mailbox_namespace": mailbox_namespace,
        },
        state={
            "fact_count": len(packet.get("payload", {}).get("facts", [])),
            "query_output_preview": compact_facts(query_output),
            "graph_freshness_status": freshness["status"],
            "graph_freshness_reasons": freshness["reasons"],
            "graph_query_used": graph_query_used,
            "pathfinder_anchor_id": pathfinder_bundle.get("anchor_id"),
            "pathfinder_bundle_mode": pathfinder_bundle.get("bundle_mode"),
        },
    )
    return {"packet": packet, "query_output": query_output, "pathfinder_bundle": pathfinder_bundle}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Graphify-backed deep search and emit a graph_hint packet.")
    parser.add_argument("--profile", default="wiki")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--parent-question-id", default=None)
    parser.add_argument("--mailbox-namespace", default=None)
    parser.add_argument("--question", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = execute_deep_search(
        profile=args.profile,
        session_id=args.session_id,
        question=args.question,
        parent_question_id=args.parent_question_id,
        mailbox_namespace=args.mailbox_namespace,
    )
    print(json.dumps({"message_id": result["packet"]["message_id"], "query_output": result["query_output"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

