from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

from delivery.mailbox_schema import validate_message
from delivery.support_bundle import validate_support_bundle
from harness_common import utc_now_iso


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
ORIGIN_SHORTCUT_RESULT_SCHEMA_PATH = CONTRACTS_ROOT / "origin_shortcut_result.v1.schema.json"
MAX_EVIDENCE_PREVIEW_CHARS = 280


@lru_cache(maxsize=1)
def load_origin_shortcut_result_schema() -> dict[str, Any]:
    return json.loads(ORIGIN_SHORTCUT_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_origin_shortcut_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_origin_shortcut_result_schema())


def _non_empty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _candidate_shortcuts(support_bundle: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    canonical_note = _non_empty(support_bundle.get("canonical_note"))
    if canonical_note:
        yield ("canonical_note", canonical_note)

    provenance_note = _non_empty(support_bundle.get("provenance_note"))
    if provenance_note:
        yield ("provenance_note", provenance_note)

    for source_path in support_bundle.get("source_paths") or []:
        source = _non_empty(source_path)
        if source:
            yield ("source_path", source)

    pathfinder_bundle = support_bundle.get("pathfinder_bundle")
    if isinstance(pathfinder_bundle, Mapping):
        for source_path in pathfinder_bundle.get("source_paths") or []:
            source = _non_empty(source_path)
            if source:
                yield ("pathfinder_source_path", source)


def _resolve_shortcut_path(shortcut_path: str, *, workspace_root: Path) -> Path:
    path = Path(shortcut_path)
    if path.is_absolute():
        return path.resolve()
    return (workspace_root / path).resolve()


def _read_evidence_preview(resolved_path: Path, *, workspace_root: Path) -> str | None:
    try:
        resolved_path.relative_to(workspace_root.resolve())
    except ValueError:
        return None
    if not resolved_path.exists() or not resolved_path.is_file():
        return None
    text = resolved_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    preview = " ".join(lines)[:MAX_EVIDENCE_PREVIEW_CHARS].strip()
    return preview or None


def follow_origin_shortcut(
    support_bundle: Mapping[str, Any],
    *,
    workspace_root: Path,
) -> dict[str, Any]:
    validate_support_bundle(support_bundle)
    active_workspace = workspace_root.resolve()
    for shortcut_kind, shortcut_path in _candidate_shortcuts(support_bundle):
        resolved_path = _resolve_shortcut_path(shortcut_path, workspace_root=active_workspace)
        exists = resolved_path.exists()
        result = {
            "schema_version": "origin_shortcut_result.v1",
            "source_packet_id": str(support_bundle["source_packet_id"]),
            "source_packet_type": str(support_bundle["source_packet_type"]),
            "query_text": str(support_bundle["query_text"]),
            "shortcut_kind": shortcut_kind,
            "shortcut_path": shortcut_path,
            "resolved_path": str(resolved_path),
            "exists": exists,
            "evidence_preview": _read_evidence_preview(resolved_path, workspace_root=active_workspace),
        }
        validate_origin_shortcut_result(result)
        return result

    result = {
        "schema_version": "origin_shortcut_result.v1",
        "source_packet_id": str(support_bundle["source_packet_id"]),
        "source_packet_type": str(support_bundle["source_packet_type"]),
        "query_text": str(support_bundle["query_text"]),
        "shortcut_kind": "none",
        "shortcut_path": None,
        "resolved_path": None,
        "exists": False,
        "evidence_preview": None,
    }
    validate_origin_shortcut_result(result)
    return result


def build_origin_shortcut_result_packet(
    *,
    provider_id: str,
    profile: str,
    session_id: str | None,
    result: Mapping[str, Any],
    parent_question_id: str | None = None,
    producer: str = "origin-shortcut-roundtrip",
) -> dict[str, Any]:
    validate_origin_shortcut_result(result)
    source_paths = [str(result["resolved_path"])] if result.get("resolved_path") else []
    packet = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "operator_brief",
        "kind": "packet",
        "parent_question_id": parent_question_id,
        "producer": producer,
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "medium",
        "scope": {
            "provider_id": provider_id,
            "profile": profile,
            "topic": str(result["query_text"]),
        },
        "payload": {
            "origin_shortcut_result": dict(result),
            "facts": [str(result.get("evidence_preview") or "Origin shortcut resolved without readable preview.")],
            "source_paths": source_paths,
            "relevance_score": 1.0 if result.get("exists") else 0.0,
            "confidence_score": 1.0 if result.get("exists") else 0.0,
        },
        "human_summary": f"Origin shortcut {str(result['shortcut_kind'])} exists={bool(result['exists'])}.",
    }
    if session_id:
        packet["scope"]["session_id"] = session_id
    validate_message(packet)
    return packet
