from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from common.map_identity import normalize_key
from harness_common import utc_now_iso


TOPIC_INDEX_ENTRY_SCHEMA_VERSION = "vault_topic_index_entry.v1"
TOPIC_INDEX_FILENAME = "index.jsonl"
TOPIC_INDEX_REF = "vault-index-ref://openyggdrasil/vault/index.jsonl"
FORBIDDEN_INDEX_TEXT = (
    "d:/",
    "d:\\",
    "c:/",
    "c:\\",
    "file://",
    "transcript.txt",
    "api_key",
    "apikey",
    "credential",
    "secret",
    ".env",
)


def topic_index_path(*, vault_root: Path) -> Path:
    return vault_root / TOPIC_INDEX_FILENAME


def _topic_key_from_topic_id(topic_id: str) -> str:
    if not topic_id.startswith("topic:"):
        raise ValueError("topic_id must start with topic:")
    return normalize_key(topic_id.split(":", 1)[1])


def _safe_text(value: Any, *, fallback: str = "") -> str:
    return " ".join(str(value or fallback).split()).strip()


def _assert_portable_entry(entry: Mapping[str, Any]) -> None:
    serialized = json.dumps(dict(entry), ensure_ascii=False, sort_keys=True).replace("\\", "/").lower()
    for forbidden in FORBIDDEN_INDEX_TEXT:
        if forbidden.lower().replace("\\", "/") in serialized:
            raise ValueError(f"topic index entry contains forbidden text: {forbidden}")


def validate_topic_index_entry(entry: Mapping[str, Any]) -> None:
    if entry.get("schema_version") != TOPIC_INDEX_ENTRY_SCHEMA_VERSION:
        raise ValueError("Invalid topic index entry schema_version")
    for key in ("topic_id", "topic_key", "title", "canonical_relative_path", "last_updated"):
        if not _safe_text(entry.get(key)):
            raise ValueError(f"topic index entry requires {key}")
    topic_key = normalize_key(str(entry["topic_key"]))
    if _topic_key_from_topic_id(str(entry["topic_id"])) != topic_key:
        raise ValueError("topic index topic_id/topic_key mismatch")
    canonical_relative_path = str(entry["canonical_relative_path"])
    if canonical_relative_path != f"queries/{topic_key}.md":
        raise ValueError("topic index canonical_relative_path mismatch")
    episode_count = entry.get("episode_count")
    if not isinstance(episode_count, int) or episode_count < 0:
        raise ValueError("topic index episode_count must be a non-negative integer")
    _assert_portable_entry(entry)


def build_topic_index_entry(
    *,
    topic_id: str,
    title: str,
    topic_key: str | None = None,
    episode_count: int = 0,
    one_line_summary: str | None = None,
    last_updated: str | None = None,
) -> dict[str, Any]:
    key = normalize_key(topic_key or _topic_key_from_topic_id(topic_id))
    entry = {
        "schema_version": TOPIC_INDEX_ENTRY_SCHEMA_VERSION,
        "topic_id": str(topic_id),
        "topic_key": key,
        "title": _safe_text(title, fallback=key.replace("-", " ").title()),
        "canonical_relative_path": f"queries/{key}.md",
        "episode_count": int(episode_count),
        "last_updated": last_updated or utc_now_iso(),
        "one_line_summary": _safe_text(one_line_summary),
    }
    validate_topic_index_entry(entry)
    return entry


def load_topic_index(*, vault_root: Path) -> list[dict[str, Any]]:
    path = topic_index_path(vault_root=vault_root)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            entry = json.loads(stripped)
            validate_topic_index_entry(entry)
            entries.append(dict(entry))
    return sorted(entries, key=lambda item: str(item["topic_key"]))


def write_topic_index(*, vault_root: Path, entries: Sequence[Mapping[str, Any]]) -> Path:
    path = topic_index_path(vault_root=vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [dict(entry) for entry in entries]
    for entry in normalized:
        validate_topic_index_entry(entry)
    with path.open("w", encoding="utf-8") as handle:
        for entry in sorted(normalized, key=lambda item: str(item["topic_key"])):
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def upsert_topic_index_entry(
    *,
    vault_root: Path,
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = dict(entry)
    validate_topic_index_entry(candidate)
    entries = [
        existing
        for existing in load_topic_index(vault_root=vault_root)
        if existing["topic_id"] != candidate["topic_id"] and existing["topic_key"] != candidate["topic_key"]
    ]
    entries.append(candidate)
    write_topic_index(vault_root=vault_root, entries=entries)
    return {
        "schema_version": "vault_topic_index_update_result.v1",
        "status": "updated",
        "index_ref": TOPIC_INDEX_REF,
        "entry_count": len(entries),
        "entry": candidate,
        "updated_at": candidate["last_updated"],
    }


def upsert_topic_index_from_placement(
    *,
    vault_root: Path,
    placement_verdict: Mapping[str, Any],
    one_line_summary: str | None = None,
) -> dict[str, Any]:
    topic_id = str(placement_verdict["topic_id"])
    topic_key = _topic_key_from_topic_id(topic_id)
    existing = {
        entry["topic_id"]: entry
        for entry in load_topic_index(vault_root=vault_root)
    }.get(topic_id)
    previous_count = int(existing.get("episode_count", 0)) if existing else 0
    placement_mode = str(placement_verdict.get("placement_mode") or "")
    episode_increment = 0 if placement_mode.endswith("existing_episode") else 1
    entry = build_topic_index_entry(
        topic_id=topic_id,
        topic_key=topic_key,
        title=str(placement_verdict.get("topic_title") or topic_key),
        episode_count=max(previous_count + episode_increment, 1),
        one_line_summary=one_line_summary or placement_verdict.get("summary"),
        last_updated=str(placement_verdict.get("evaluated_at") or utc_now_iso()),
    )
    return upsert_topic_index_entry(vault_root=vault_root, entry=entry)


def find_topic_index_entries(
    *,
    vault_root: Path,
    query_text: str | None = None,
    topic_key: str | None = None,
) -> list[dict[str, Any]]:
    entries = load_topic_index(vault_root=vault_root)
    if topic_key:
        wanted = normalize_key(topic_key)
        return [entry for entry in entries if entry["topic_key"] == wanted]
    if not query_text:
        return entries
    tokens = {
        token
        for token in normalize_key(query_text).replace("/", "-").split("-")
        if len(token) > 2
    }
    if not tokens:
        return entries
    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in entries:
        haystack = normalize_key(
            " ".join(
                [
                    str(entry.get("topic_key") or ""),
                    str(entry.get("title") or ""),
                    str(entry.get("one_line_summary") or ""),
                ]
            )
        )
        score = sum(1 for token in tokens if token in haystack)
        if score:
            scored.append((score, entry))
    return [entry for _, entry in sorted(scored, key=lambda item: (-item[0], item[1]["topic_key"]))]
