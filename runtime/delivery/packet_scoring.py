from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from delivery.mailbox_store import MAILBOX_INBOX_ROOT, inbox_packets


def score_packet(message: Dict[str, Any], query_text: str) -> float:
    haystacks: List[str] = []
    scope = message.get("scope", {})
    payload = message.get("payload", {})
    for value in [scope.get("topic"), message.get("human_summary")]:
        if value:
            haystacks.append(str(value).lower())
    for item in payload.get("facts", []):
        haystacks.append(str(item).lower())
    for item in payload.get("source_paths", []):
        haystacks.append(str(item).lower())
    query_tokens = [token.lower() for token in query_text.split() if len(token) >= 2]
    if not query_tokens:
        return float(payload.get("relevance_score", 0.0))
    matched = 0
    for token in query_tokens:
        if any(token in haystack for haystack in haystacks):
            matched += 1
    base = float(payload.get("relevance_score", 0.0))
    return base + (matched / max(len(query_tokens), 1))


def select_inbox_packets(
    *,
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    query_text: str,
    top_k: int = 3,
    inbox_root: Path = MAILBOX_INBOX_ROOT,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    packets = inbox_packets(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        inbox_root=inbox_root,
        namespace=namespace,
    )
    ranked = sorted(
        packets,
        key=lambda message: score_packet(message, query_text),
        reverse=True,
    )
    return ranked[:top_k]
