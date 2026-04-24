from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set

from harness_common import DEFAULT_VAULT, utc_now_iso
from mailbox_schema import validate_message
from packet_factory import default_delivery
from plugin_logger import record_plugin_event
from postman_gateway import submit_packet


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
VAULT_ROOT = DEFAULT_VAULT
TARGET_DIRS = ("queries", "concepts", "entities", "comparisons")


def iter_note_paths(vault_root: Path) -> List[Path]:
    paths: List[Path] = []
    for directory in TARGET_DIRS:
        root = vault_root / directory
        if not root.exists():
            continue
        paths.extend(sorted(root.rglob("*.md")))
    return paths


def slug_to_note_key(path: Path, *, vault_root: Path) -> str:
    relative = path.resolve().relative_to(vault_root.resolve()).as_posix()
    no_ext = relative[:-3] if relative.endswith(".md") else relative
    return no_ext


def extract_wikilinks(text: str) -> List[str]:
    links: List[str] = []
    for raw in WIKILINK_RE.findall(text):
        target = raw.split("|", 1)[0].strip()
        if not target:
            continue
        links.append(target.replace("\\", "/").removesuffix(".md"))
    return links


def normalize_index_targets(index_text: str) -> Set[str]:
    targets: Set[str] = set()
    for link in extract_wikilinks(index_text):
        targets.add(link)
        if not link.startswith(("queries/", "concepts/", "entities/", "comparisons/")):
            targets.add(f"queries/{link}")
            targets.add(f"concepts/{link}")
            targets.add(f"entities/{link}")
            targets.add(f"comparisons/{link}")
    return targets


def lint_vault(*, vault_root: Path = VAULT_ROOT) -> Dict[str, object]:
    note_paths = iter_note_paths(vault_root)
    note_keys = {slug_to_note_key(path, vault_root=vault_root): path for path in note_paths}

    inbound: Dict[str, int] = {key: 0 for key in note_keys}
    broken_links: List[Dict[str, str]] = []

    for path in note_paths:
        text = path.read_text(encoding="utf-8")
        source_key = slug_to_note_key(path, vault_root=vault_root)
        for link in extract_wikilinks(text):
            candidate_keys = [link]
            if not link.startswith(("queries/", "concepts/", "entities/", "comparisons/")):
                candidate_keys.extend(
                    [
                        f"queries/{link}",
                        f"concepts/{link}",
                        f"entities/{link}",
                        f"comparisons/{link}",
                    ]
                )

            matched = False
            for candidate in candidate_keys:
                if candidate in note_keys:
                    inbound[candidate] += 1
                    matched = True
                    break
            if not matched:
                broken_links.append({"source": source_key, "target": link})

    index_path = vault_root / "index.md"
    index_targets = normalize_index_targets(index_path.read_text(encoding="utf-8")) if index_path.exists() else set()
    missing_from_index = sorted(key for key in note_keys if key not in index_targets)
    orphan_notes = sorted(key for key, count in inbound.items() if count == 0)

    issue_count = len(broken_links) + len(missing_from_index) + len(orphan_notes)
    return {
        "note_count": len(note_paths),
        "broken_links": broken_links,
        "broken_link_count": len(broken_links),
        "missing_from_index": missing_from_index,
        "missing_from_index_count": len(missing_from_index),
        "orphan_notes": orphan_notes,
        "orphan_note_count": len(orphan_notes),
        "issue_count": issue_count,
    }


def lint_alert_packet(
    *,
    profile: str,
    session_id: str | None,
    parent_question_id: str | None,
    summary: Dict[str, object],
    vault_root: Path = VAULT_ROOT,
    producer: str = "lint-executor",
) -> Dict[str, object]:
    broken_links = summary.get("broken_links", [])
    missing_from_index = summary.get("missing_from_index", [])
    orphan_notes = summary.get("orphan_notes", [])
    facts: List[str] = [
        f"broken_link_count={summary['broken_link_count']}",
        f"missing_from_index_count={summary['missing_from_index_count']}",
        f"orphan_note_count={summary['orphan_note_count']}",
    ]
    human_summary = (
        f"Lint found {summary['issue_count']} issues "
        f"(broken={summary['broken_link_count']}, index={summary['missing_from_index_count']}, orphan={summary['orphan_note_count']})."
    )
    source_paths: List[str] = [str((vault_root / "index.md").resolve())]
    source_paths.extend(str((vault_root / f"{key}.md").resolve()) for key in list(missing_from_index)[:3])
    source_paths.extend(str((vault_root / f"{item['source']}.md").resolve()) for item in list(broken_links)[:3])

    scope = {
        "profile": profile,
        "vault_path": str(vault_root.resolve()),
        "topic": "llm-wiki lint",
    }
    if session_id:
        scope["session_id"] = session_id

    packet = {
        "schema_version": "mailbox.v1",
        "message_id": __import__("uuid").uuid4().hex,
        "message_type": "lint_alert",
        "kind": "packet",
        "parent_question_id": parent_question_id,
        "producer": producer,
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "high" if summary["issue_count"] else "low",
        "scope": scope,
        "payload": {
            "source_paths": source_paths,
            "facts": facts,
            "lint_summary": summary,
            "relevance_score": 0.9 if summary["issue_count"] else 0.3,
            "confidence_score": 0.95,
        },
        "delivery": default_delivery(profile=profile, session_id=session_id),
        "human_summary": human_summary,
    }
    validate_message(packet)
    return packet


def execute_lint(
    *,
    profile: str,
    session_id: str | None,
    parent_question_id: str | None = None,
    mailbox_namespace: str | None = None,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, object]:
    summary = lint_vault(vault_root=vault_root)
    packet = lint_alert_packet(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        summary=summary,
        vault_root=vault_root,
        producer="lint-executor",
    )
    submit_packet(packet, namespace=mailbox_namespace)
    record_plugin_event(
        event_type="lint_alert_generated",
        actor="lint_executor",
        parent_question_id=parent_question_id,
        profile=profile,
        session_id=session_id,
        query_text="llm-wiki lint",
        artifacts={
            "packet_id": packet["message_id"],
            "packet_type": packet["message_type"],
            "mailbox_namespace": mailbox_namespace,
        },
        state={
            "issue_count": summary["issue_count"],
            "broken_link_count": summary["broken_link_count"],
            "missing_from_index_count": summary["missing_from_index_count"],
            "orphan_note_count": summary["orphan_note_count"],
        },
    )
    return {"summary": summary, "packet": packet}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic LLM Wiki lint and emit a lint_alert packet.")
    parser.add_argument("--profile", default="wiki")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--parent-question-id", default=None)
    parser.add_argument("--mailbox-namespace", default=None)
    parser.add_argument("--vault", type=Path, default=VAULT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = execute_lint(
        profile=args.profile,
        session_id=args.session_id,
        parent_question_id=args.parent_question_id,
        mailbox_namespace=args.mailbox_namespace,
        vault_root=args.vault,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

