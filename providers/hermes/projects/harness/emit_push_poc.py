from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from mailbox_common import emit_graph_hint_poc


CENTRAL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_PATHS = [
    CENTRAL_ROOT
    / "vault"
    / "queries"
    / "what-is-the-role-of-an-external-single-writer-harness-in-the-hermes-architecture-answer-in-exact.md",
    CENTRAL_ROOT / "vault" / "concepts" / "llm-wiki-pattern.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit one push-ready mailbox packet for the reverse-push POC."
    )
    parser.add_argument("--profile", default="wiki")
    parser.add_argument("--session-id", default="push-poc-session")
    parser.add_argument("--parent-question-id", default=None)
    parser.add_argument("--mailbox-namespace", default=None)
    parser.add_argument("--topic", default="mailbox reverse push")
    parser.add_argument("--source-path", action="append", default=None)
    return parser.parse_args()


def default_facts() -> List[str]:
    return [
        "mailbox packet is not a second SOT",
        "Graphify is the unified query surface over the LLM Wiki SOT",
        "push-ready packets should be delivered into a Hermes-consumable inbox",
    ]


def resolve_source_paths(source_paths: List[str] | None) -> List[str]:
    if source_paths:
        return [str(Path(path).resolve()) for path in source_paths]
    return [str(path.resolve()) for path in DEFAULT_SOURCE_PATHS if path.exists()]


def main() -> int:
    args = parse_args()
    message = emit_graph_hint_poc(
        profile=args.profile,
        session_id=args.session_id,
        mailbox_namespace=args.mailbox_namespace,
        parent_question_id=args.parent_question_id,
        topic=args.topic,
        source_paths=resolve_source_paths(args.source_path),
        facts=default_facts(),
        human_summary="Background search finished and produced a push-ready graph hint packet.",
    )
    print(json.dumps(message, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
