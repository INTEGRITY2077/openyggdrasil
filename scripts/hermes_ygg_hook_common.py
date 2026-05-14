from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.capture.provider_current_source_bridge import (  # noqa: E402
    build_memory_ticket_payload_from_existing_provider_exchange,
)
from runtime.delivery.postman_native_activation import activate_native_lane  # noqa: E402
from runtime.delivery.postman_live_delivery import (  # noqa: E402
    PostmanIntegrityError,
    submit_live_delivery,
)
from source_ref.hermes_session_json import _canonical_anchor_hash  # noqa: E402


POSTMAN_DIR = Path.home() / ".yggdrasil" / "sessions" / "postman"
STATE_PATH = POSTMAN_DIR / "provider_admission_hook_state.jsonl"
LOG_PATH = POSTMAN_DIR / "provider_admission_hook_log.jsonl"
RECALL_STATE_PATH = POSTMAN_DIR / "provider_recall_hook_state.jsonl"
RECALL_LOG_PATH = POSTMAN_DIR / "provider_recall_hook_log.jsonl"
DEFAULT_RECIPIENT = "MS1"
DEFAULT_RECALL_RECIPIENT = "MF1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def _read_stdin_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"_decode_error": True, "_raw_prefix": raw[:200]}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _session_id_from_name(path: Path) -> str:
    name = path.name
    if name.startswith("session_") and name.endswith(".json"):
        return name[len("session_") : -len(".json")]
    return path.stem


def _session_path_from_event(event: Mapping[str, Any]) -> Path | None:
    session_id = str(event.get("session_id") or "").strip()
    candidates: list[Path] = []
    if session_id:
        candidates.append(Path.home() / ".hermes" / "sessions" / f"session_{session_id}.json")
        for path in (Path.home() / ".hermes" / "profiles").glob("*/sessions"):
            candidates.append(path / f"session_{session_id}.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    roots = [Path.home() / ".hermes" / "sessions"]
    roots.extend((Path.home() / ".hermes" / "profiles").glob("*/sessions"))
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(root.glob("session_*.json"))
    if not files:
        return None
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0]


def _load_session(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _message_text(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _latest_user_assistant_range(messages: list[dict[str, Any]]) -> tuple[int, int, str, str, list[dict[str, Any]]] | None:
    for index in range(len(messages) - 2, -1, -1):
        first = messages[index]
        second = messages[index + 1]
        if first.get("role") != "user" or second.get("role") != "assistant":
            continue
        user_text = _message_text(first)
        assistant_text = _message_text(second)
        if user_text and assistant_text:
            selected = [first, second]
            return index, index + 1, user_text, assistant_text, selected
    return None


def _seen_keys() -> set[str]:
    return _seen_keys_from(STATE_PATH)


def _seen_keys_from(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return seen
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, Mapping) and row.get("dedupe_key"):
            seen.add(str(row["dedupe_key"]))
    return seen


def _latest_user_message(messages: list[dict[str, Any]]) -> tuple[int, str] | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") != "user":
            continue
        text = _message_text(message)
        if text:
            return index, text
    return None


def _event_query_text(event: Mapping[str, Any]) -> str:
    candidates: list[Any] = [
        event.get("query"),
        event.get("query_text"),
        event.get("prompt"),
        event.get("text"),
    ]
    for key in ("tool_input", "input", "arguments", "params"):
        value = event.get(key)
        if isinstance(value, Mapping):
            candidates.extend(
                [
                    value.get("query"),
                    value.get("query_text"),
                    value.get("prompt"),
                    value.get("text"),
                ]
            )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return " ".join(candidate.split())
    return ""


def _hash_text(value: str) -> str:
    return _canonical_anchor_hash([{"role": "user", "content": value}])


def run_latest_provider_recall_hook(*, event_name: str, require_tool_name: str | None = None) -> dict[str, Any]:
    """Turn a Provider recall tool attempt into a product-shaped MF query.

    The hook is intentionally narrow: it sends only the current user-facing
    question text as `query_text`. It does not send source refs, support paths,
    worker instructions, or validation vocabulary.
    """

    event = _read_stdin_event()
    tool_name = str(event.get("tool_name") or "").strip()
    if require_tool_name and tool_name != require_tool_name:
        return {"status": "ignored", "reason_code": "tool_name_not_matched", "event_name": event_name}

    session_path = _session_path_from_event(event)
    if session_path is None:
        result = {"status": "typed_unavailable", "reason_code": "session_path_not_found", "event_name": event_name}
        _append_jsonl(RECALL_LOG_PATH, {**result, "created_at": _now(), "tool_name": tool_name})
        return result

    payload = _load_session(session_path)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        result = {"status": "typed_unavailable", "reason_code": "session_messages_missing", "event_name": event_name}
        _append_jsonl(RECALL_LOG_PATH, {**result, "created_at": _now(), "tool_name": tool_name, "session_path_name": session_path.name})
        return result

    normalized_messages = [dict(row) for row in messages if isinstance(row, Mapping)]
    latest_user = _latest_user_message(normalized_messages)
    query_text = _event_query_text(event)
    if not query_text and latest_user:
        query_text = latest_user[1]
    if not query_text:
        result = {"status": "skipped", "reason_code": "query_text_missing", "event_name": event_name}
        _append_jsonl(RECALL_LOG_PATH, {**result, "created_at": _now(), "tool_name": tool_name, "session_path_name": session_path.name})
        return result

    session_id = str(payload.get("provider_session_id") or payload.get("session_id") or _session_id_from_name(session_path))
    user_index = latest_user[0] if latest_user else -1
    query_hash = _hash_text(query_text)
    dedupe_key = f"provider-recall:{session_id}:{user_index}:{query_hash}"
    if dedupe_key in _seen_keys_from(RECALL_STATE_PATH):
        result = {
            "status": "skipped",
            "reason_code": "already_processed",
            "event_name": event_name,
            "provider_session_id": session_id,
            "user_message_index": user_index,
            "query_hash": query_hash,
        }
        _append_jsonl(RECALL_LOG_PATH, {**result, "created_at": _now(), "tool_name": tool_name, "session_path_name": session_path.name})
        return result

    try:
        delivery = submit_live_delivery(
            recipient=DEFAULT_RECALL_RECIPIENT,
            message_type="query",
            payload={"query_text": query_text},
            provider_id="hermes",
        )
        try:
            activation = activate_native_lane(
                op=DEFAULT_RECALL_RECIPIENT,
                label="MF1",
                role_type="consumer",
                session="ygg-mf1",
                delivery=delivery,
                message_type="query",
                payload={"query_text": query_text},
                registry_dir=Path.home() / ".yggdrasil",
                sessions_dir=Path.home() / ".yggdrasil" / "sessions",
            )
        except OSError as exc:
            activation = {"status": "blocked", "reason_code": f"native_activation_unavailable:{exc.__class__.__name__}"}
        status = "delivered"
        reason_code = "find_request_delivered"
    except PostmanIntegrityError as exc:
        delivery = exc.result
        activation = {}
        status = "rejected"
        reason_code = str(delivery.get("reason") or "postman_integrity_rejected")

    result = {
        "status": status,
        "reason_code": reason_code,
        "event_name": event_name,
        "provider_session_id": session_id,
        "user_message_index": user_index,
        "query_hash": query_hash,
        "delivery_id": delivery.get("delivery_id"),
        "mail_id": delivery.get("mail_id"),
        "work_order_id": delivery.get("work_order_id"),
        "recipient": delivery.get("recipient"),
        "postman_activation_status": activation.get("status"),
        "hard_nonclaims": [
            "recall_delivery_is_not_support_bundle",
            "provider_question_text_only_no_source_ref_or_support_paths",
            "postman_does_not_judge_recall_answer",
        ],
    }
    _append_jsonl(RECALL_STATE_PATH, {**result, "created_at": _now(), "dedupe_key": dedupe_key})
    _append_jsonl(RECALL_LOG_PATH, {**result, "created_at": _now(), "tool_name": tool_name, "session_path_name": session_path.name})
    return result


def run_latest_provider_admission_hook(*, event_name: str, require_tool_name: str | None = None) -> dict[str, Any]:
    event = _read_stdin_event()
    if require_tool_name and str(event.get("tool_name") or "") != require_tool_name:
        return {"status": "ignored", "reason_code": "tool_name_not_matched", "event_name": event_name}

    session_path = _session_path_from_event(event)
    if session_path is None:
        result = {"status": "typed_unavailable", "reason_code": "session_path_not_found", "event_name": event_name}
        _append_jsonl(LOG_PATH, {**result, "created_at": _now()})
        return result

    payload = _load_session(session_path)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        result = {"status": "typed_unavailable", "reason_code": "session_messages_missing", "event_name": event_name}
        _append_jsonl(LOG_PATH, {**result, "created_at": _now(), "session_path_name": session_path.name})
        return result
    normalized_messages = [dict(row) for row in messages if isinstance(row, Mapping)]
    latest = _latest_user_assistant_range(normalized_messages)
    if latest is None:
        result = {"status": "typed_unavailable", "reason_code": "latest_user_assistant_range_missing", "event_name": event_name}
        _append_jsonl(LOG_PATH, {**result, "created_at": _now(), "session_path_name": session_path.name})
        return result

    start, end, user_text, assistant_text, selected = latest
    session_id = str(payload.get("provider_session_id") or payload.get("session_id") or _session_id_from_name(session_path))
    anchor_hash = _canonical_anchor_hash(selected)
    source_ref = f"hermes-session-json://{session_id}"
    dedupe_key = f"{source_ref}:{start}:{end}:{anchor_hash}"
    if dedupe_key in _seen_keys():
        result = {
            "status": "skipped",
            "reason_code": "already_processed",
            "event_name": event_name,
            "source_ref": source_ref,
            "message_index_range": {"start": start, "end": end},
        }
        _append_jsonl(LOG_PATH, {**result, "created_at": _now(), "session_path_name": session_path.name})
        return result

    ticket = build_memory_ticket_payload_from_existing_provider_exchange(
        provider_id="hermes",
        provider_profile="openyggdrasil-provider",
        provider_session_id=session_id,
        user_text=user_text,
        assistant_text=assistant_text,
        message_index_range={"start": start, "end": end},
        anchor_hash=anchor_hash,
        sessions_dir=session_path.parent,
        source_ref_scheme="hermes-session-json",
    )
    if ticket.get("schema_version") != "memory_ticket.v1" or ticket.get("status") == "typed_unavailable":
        reason_code = str(ticket.get("reason_code") or "memory_ticket_not_emitted")
        result = {
            "status": "skipped",
            "reason_code": reason_code,
            "event_name": event_name,
            "source_ref": source_ref,
            "message_index_range": {"start": start, "end": end},
        }
        _append_jsonl(STATE_PATH, {**result, "created_at": _now(), "dedupe_key": dedupe_key, "anchor_hash": anchor_hash})
        _append_jsonl(LOG_PATH, {**result, "created_at": _now(), "session_path_name": session_path.name})
        return result

    try:
        delivery = submit_live_delivery(
            recipient=DEFAULT_RECIPIENT,
            message_type="memory_ticket",
            payload=ticket,
            provider_id="hermes",
            mail_id=f"memticket-{uuid.uuid4().hex[:6]}",
        )
        status = "delivered"
        reason_code = "memory_ticket_delivered"
    except PostmanIntegrityError as exc:
        delivery = exc.result
        status = "rejected"
        reason_code = str(delivery.get("reason") or "postman_integrity_rejected")

    result = {
        "status": status,
        "reason_code": reason_code,
        "event_name": event_name,
        "source_ref": source_ref,
        "message_index_range": {"start": start, "end": end},
        "anchor_hash": anchor_hash,
        "canonical_topic_key": ticket.get("canonical_topic_key"),
        "delivery_id": delivery.get("delivery_id"),
        "mail_id": delivery.get("mail_id"),
        "work_order_id": delivery.get("work_order_id"),
        "recipient": delivery.get("recipient"),
    }
    _append_jsonl(STATE_PATH, {**result, "created_at": _now(), "dedupe_key": dedupe_key})
    _append_jsonl(LOG_PATH, {**result, "created_at": _now(), "session_path_name": session_path.name})
    return result
