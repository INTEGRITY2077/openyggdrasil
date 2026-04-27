from __future__ import annotations

import hashlib
import json
import uuid
import shutil
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from delivery.mailbox_schema import validate_message
from delivery.packet_factory import is_push_ready_packet
from harness_common import OPS_ROOT, append_jsonl, json_ready, read_jsonl, utc_now_iso


MAILBOX_ROOT = OPS_ROOT / "mailbox"
MAILBOX_MESSAGES_PATH = MAILBOX_ROOT / "messages.jsonl"
MAILBOX_CLAIMS_PATH = MAILBOX_ROOT / "claims.jsonl"
MAILBOX_INBOX_ROOT = MAILBOX_ROOT / "inbox"
MAILBOX_OPERATOR_ROOT = MAILBOX_ROOT / "operator"
MAILBOX_NAMESPACE_ROOT = MAILBOX_ROOT / "namespaces"
MAILBOX_ARCHIVE_ROOT = MAILBOX_ROOT / "archive"
MAILBOX_CLEARINGHOUSE_EVENTS_PATH = MAILBOX_ROOT / "events.jsonl"
MAILBOX_ACTIVE_NAMESPACE = "active"
QUESTION_INBOX_PREFIX = "question__"
GLOBAL_INBOX_KEY = "global"
SAFE_INBOX_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")
MAILBOX_CLEARINGHOUSE_EVENT_SCHEMA_VERSION = "mailbox_clearinghouse_event.v1"
MAILBOX_CLEARINGHOUSE_RESULT_SCHEMA_VERSION = "mailbox_clearinghouse_result.v1"
MAILBOX_CLEARINGHOUSE_CONSUMER = "mailbox-clearinghouse"
MAILBOX_CLEARINGHOUSE_CLAIM_TYPE = "clearinghouse_event_recorded"


def mailbox_root_for(*, namespace: str | None = None) -> Path:
    normalized = (namespace or "").strip()
    if not normalized or normalized == MAILBOX_ACTIVE_NAMESPACE:
        return MAILBOX_ROOT
    return MAILBOX_NAMESPACE_ROOT / normalized


def mailbox_paths(*, namespace: str | None = None) -> Dict[str, Path]:
    root = mailbox_root_for(namespace=namespace)
    return {
        "root": root,
        "messages_path": root / "messages.jsonl",
        "claims_path": root / "claims.jsonl",
        "events_path": root / "events.jsonl",
        "inbox_root": root / "inbox",
        "operator_root": root / "operator",
        "status_path": root / "latest-status.json",
    }


def ensure_mailbox_dirs(*, namespace: str | None = None) -> Dict[str, Path]:
    paths = mailbox_paths(namespace=namespace)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["inbox_root"].mkdir(parents=True, exist_ok=True)
    paths["operator_root"].mkdir(parents=True, exist_ok=True)
    MAILBOX_ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    return paths


def namespace_exists(namespace: str | None) -> bool:
    return mailbox_root_for(namespace=namespace).exists()


def archive_namespace(*, namespace: str, reason: str | None = None) -> Path:
    normalized = namespace.strip()
    if not normalized or normalized == MAILBOX_ACTIVE_NAMESPACE:
        raise ValueError("Refusing to archive the active mailbox root")
    source_root = mailbox_root_for(namespace=normalized)
    if not source_root.exists():
        raise FileNotFoundError(f"Mailbox namespace does not exist: {normalized}")
    MAILBOX_ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    destination = MAILBOX_ARCHIVE_ROOT / f"{utc_now_iso().replace(':', '').replace('+00:00', 'Z')}-{normalized}"
    shutil.move(str(source_root), str(destination))
    if reason:
        (destination / "archive-reason.txt").write_text(reason + "\n", encoding="utf-8")
    return destination


def read_messages(
    path: Path | None = None,
    *,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    target_path = path or mailbox_paths(namespace=namespace)["messages_path"]
    return read_jsonl(target_path)


def read_claims(
    path: Path | None = None,
    *,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    target_path = path or mailbox_paths(namespace=namespace)["claims_path"]
    return read_jsonl(target_path)


def append_message(
    message: Dict[str, Any],
    *,
    path: Path | None = None,
    namespace: str | None = None,
) -> Dict[str, Any]:
    ensure_mailbox_dirs(namespace=namespace)
    validate_message(message)
    target_path = path or mailbox_paths(namespace=namespace)["messages_path"]
    append_jsonl(target_path, message)
    return message


def append_claim(
    *,
    message_id: str,
    consumer: str,
    claim_type: str,
    scope: Optional[Dict[str, Any]] = None,
    path: Path | None = None,
    namespace: str | None = None,
) -> Dict[str, Any]:
    claim = {
        "claim_id": uuid.uuid4().hex,
        "message_id": message_id,
        "consumer": consumer,
        "claim_type": claim_type,
        "scope": json_ready(scope or {}),
        "created_at": utc_now_iso(),
    }
    target_path = path or mailbox_paths(namespace=namespace)["claims_path"]
    append_jsonl(target_path, claim)
    return claim


def claimed_message_ids(
    *,
    consumer: Optional[str] = None,
    claim_type: Optional[str] = None,
    path: Path | None = None,
    namespace: str | None = None,
) -> set[str]:
    claimed: set[str] = set()
    for claim in read_claims(path, namespace=namespace):
        if consumer and claim.get("consumer") != consumer:
            continue
        if claim_type and claim.get("claim_type") != claim_type:
            continue
        message_id = claim.get("message_id")
        if message_id:
            claimed.add(message_id)
    return claimed


def _safe_inbox_component(raw_value: str) -> str:
    cleaned = SAFE_INBOX_COMPONENT_RE.sub("_", raw_value.strip())
    return cleaned or "unknown"


def inbox_key_for(
    *,
    session_id: Optional[str] = None,
    parent_question_id: Optional[str] = None,
) -> str:
    if session_id:
        return _safe_inbox_component(session_id)
    if parent_question_id:
        return f"{QUESTION_INBOX_PREFIX}{_safe_inbox_component(parent_question_id)}"
    return GLOBAL_INBOX_KEY


def inbox_path_for(
    message: Dict[str, Any],
    *,
    inbox_root: Path | None = None,
    namespace: str | None = None,
) -> Path:
    scope = message.get("scope", {})
    profile = scope.get("profile") or "default"
    session_id = scope.get("session_id")
    parent_question_id = message.get("parent_question_id")
    target_root = inbox_root or mailbox_paths(namespace=namespace)["inbox_root"]
    inbox_key = inbox_key_for(
        session_id=session_id,
        parent_question_id=parent_question_id,
    )
    return target_root / profile / f"{inbox_key}.jsonl"


def legacy_global_inbox_paths(
    *,
    inbox_root: Path | None = None,
    namespace: str | None = None,
) -> List[Path]:
    target_root = inbox_root or mailbox_paths(namespace=namespace)["inbox_root"]
    if not target_root.exists():
        return []
    return sorted(target_root.rglob(f"{GLOBAL_INBOX_KEY}.jsonl"))


def operator_path_for(
    message: Dict[str, Any],
    *,
    operator_root: Path | None = None,
    namespace: str | None = None,
) -> Path:
    scope = message.get("scope", {})
    profile = scope.get("profile") or "default"
    message_type = _safe_inbox_component(str(message.get("message_type") or "packet"))
    target_root = operator_root or mailbox_paths(namespace=namespace)["operator_root"]
    return target_root / profile / f"{message_type}.jsonl"


def delivery_target_for(
    message: Dict[str, Any],
    *,
    inbox_root: Path | None = None,
    operator_root: Path | None = None,
    namespace: str | None = None,
) -> tuple[str, Path]:
    scope = message.get("scope", {})
    if scope.get("session_id") or message.get("parent_question_id"):
        return (
            "hermes_inbox",
            inbox_path_for(
                message,
                inbox_root=inbox_root,
                namespace=namespace,
            ),
        )
    return (
        "operator_lane",
        operator_path_for(
            message,
            operator_root=operator_root,
            namespace=namespace,
        ),
    )


def deliver_push_packet(
    message: Dict[str, Any],
    *,
    consumer: str = "postman",
    inbox_root: Path | None = None,
    operator_root: Path | None = None,
    claims_path: Path | None = None,
    namespace: str | None = None,
) -> Path:
    validate_message(message)
    ensure_mailbox_dirs(namespace=namespace)
    _, destination = delivery_target_for(
        message,
        inbox_root=inbox_root,
        operator_root=operator_root,
        namespace=namespace,
    )
    append_jsonl(destination, message)
    append_claim(
        message_id=message["message_id"],
        consumer=consumer,
        claim_type="push_delivered",
        scope=message.get("scope"),
        path=claims_path,
        namespace=namespace,
    )
    return destination


def inbox_packets(
    *,
    profile: str,
    session_id: Optional[str] = None,
    parent_question_id: Optional[str] = None,
    inbox_root: Path | None = None,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    session_key = inbox_key_for(
        session_id=session_id,
        parent_question_id=parent_question_id,
    )
    target_root = inbox_root or mailbox_paths(namespace=namespace)["inbox_root"]
    path = target_root / profile / f"{session_key}.jsonl"
    return read_jsonl(path)


def read_clearinghouse_events(
    path: Path | None = None,
    *,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    target_path = path or mailbox_paths(namespace=namespace)["events_path"]
    return read_jsonl(target_path)


def _safe_event_scope(message: Dict[str, Any]) -> Dict[str, Any]:
    scope = message.get("scope", {})
    safe_scope = {
        "provider_id": scope.get("provider_id"),
        "profile": scope.get("profile"),
        "session_id": scope.get("session_id"),
        "topic": scope.get("topic"),
    }
    return {key: value for key, value in safe_scope.items() if value is not None}


def _payload_fingerprint(message: Dict[str, Any]) -> str:
    payload = json.dumps(
        json_ready(message.get("payload", {})),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_ref(message: Dict[str, Any]) -> tuple[str, str]:
    fingerprint = _payload_fingerprint(message)
    message_id = str(message.get("message_id") or "unknown")
    return (
        f"mailbox-payload-ref://openyggdrasil/{message_id}/{fingerprint}",
        f"sha256:{fingerprint}",
    )


def _clearinghouse_destination(
    message: Dict[str, Any],
    *,
    inbox_root: Path | None = None,
    operator_root: Path | None = None,
    namespace: str | None = None,
) -> Dict[str, Any]:
    kind = str(message.get("kind") or "")
    scope = message.get("scope", {})
    if kind == "command":
        return {
            "type": "command_queue",
            "message_type": message.get("message_type"),
            "profile": scope.get("profile"),
            "session_id": scope.get("session_id"),
        }
    route, _ = delivery_target_for(
        message,
        inbox_root=inbox_root,
        operator_root=operator_root,
        namespace=namespace,
    )
    return {
        "type": route,
        "message_type": message.get("message_type"),
        "profile": scope.get("profile"),
        "session_id": scope.get("session_id"),
    }


def build_mailbox_clearinghouse_event(
    message: Dict[str, Any],
    *,
    event_type: str,
    action: str,
    consumer: str = MAILBOX_CLEARINGHOUSE_CONSUMER,
    created_at: str | None = None,
    inbox_root: Path | None = None,
    operator_root: Path | None = None,
    namespace: str | None = None,
) -> Dict[str, Any]:
    validate_message(message)
    payload_ref, payload_fingerprint = _payload_ref(message)
    event = {
        "schema_version": MAILBOX_CLEARINGHOUSE_EVENT_SCHEMA_VERSION,
        "event_id": uuid.uuid4().hex,
        "event_type": event_type,
        "message_id": message["message_id"],
        "message_type": message["message_type"],
        "kind": message["kind"],
        "priority": message["priority"],
        "action": action,
        "consumer": consumer,
        "created_at": created_at or utc_now_iso(),
        "message_created_at": message["created_at"],
        "scope": _safe_event_scope(message),
        "destination": _clearinghouse_destination(
            message,
            inbox_root=inbox_root,
            operator_root=operator_root,
            namespace=namespace,
        ),
        "payload_ref": payload_ref,
        "payload_fingerprint": payload_fingerprint,
        "raw_payload_copied": False,
        "worker_execution_attempted": False,
    }
    validate_mailbox_clearinghouse_event(event)
    return event


def validate_mailbox_clearinghouse_event(event: Dict[str, Any]) -> None:
    if event.get("schema_version") != MAILBOX_CLEARINGHOUSE_EVENT_SCHEMA_VERSION:
        raise ValueError("Invalid mailbox clearinghouse event schema_version")
    required = {
        "event_id",
        "event_type",
        "message_id",
        "message_type",
        "kind",
        "action",
        "consumer",
        "created_at",
        "scope",
        "destination",
        "payload_ref",
        "payload_fingerprint",
        "raw_payload_copied",
        "worker_execution_attempted",
    }
    missing = sorted(key for key in required if key not in event)
    if missing:
        raise ValueError(f"Missing mailbox clearinghouse event fields: {', '.join(missing)}")
    if "payload" in event or event.get("raw_payload_copied") is not False:
        raise ValueError("Mailbox clearinghouse event must not copy raw payload")
    if event.get("worker_execution_attempted") is not False:
        raise ValueError("Mailbox clearinghouse event must not execute workers")
    if not str(event.get("payload_ref") or "").startswith("mailbox-payload-ref://openyggdrasil/"):
        raise ValueError("Mailbox clearinghouse event payload_ref must be a safe reference")
    if not str(event.get("payload_fingerprint") or "").startswith("sha256:"):
        raise ValueError("Mailbox clearinghouse event payload_fingerprint must be sha256-prefixed")
    destination = event.get("destination")
    if not isinstance(destination, dict) or "path" in destination:
        raise ValueError("Mailbox clearinghouse event destination must be path-free")


def validate_mailbox_clearinghouse_result(result: Dict[str, Any]) -> None:
    if result.get("schema_version") != MAILBOX_CLEARINGHOUSE_RESULT_SCHEMA_VERSION:
        raise ValueError("Invalid mailbox clearinghouse result schema_version")
    if result.get("clearinghouse_status") != "completed":
        raise ValueError("Mailbox clearinghouse result is not completed")
    if result.get("event_driven") is not True:
        raise ValueError("Mailbox clearinghouse result must be event driven")
    if result.get("jsonl_storage_only") is not False:
        raise ValueError("Mailbox clearinghouse result must not be JSONL-storage-only")
    if result.get("worker_execution_attempted") is not False:
        raise ValueError("Mailbox clearinghouse result must not execute workers")
    event_ids = result.get("event_ids")
    if not isinstance(event_ids, list):
        raise ValueError("Mailbox clearinghouse result event_ids must be a list")
    if result.get("events_recorded") != len(event_ids):
        raise ValueError("Mailbox clearinghouse result event count mismatch")


def clear_mailbox_events(
    *,
    messages_path: Path | None = None,
    claims_path: Path | None = None,
    events_path: Path | None = None,
    inbox_root: Path | None = None,
    operator_root: Path | None = None,
    namespace: str | None = None,
    consumer: str = MAILBOX_CLEARINGHOUSE_CONSUMER,
    created_at: str | None = None,
) -> Dict[str, Any]:
    ensure_mailbox_dirs(namespace=namespace)
    paths = mailbox_paths(namespace=namespace)
    effective_events_path = events_path or paths["events_path"]
    messages = read_messages(messages_path, namespace=namespace)
    already_cleared = claimed_message_ids(
        consumer=consumer,
        claim_type=MAILBOX_CLEARINGHOUSE_CLAIM_TYPE,
        path=claims_path,
        namespace=namespace,
    )
    already_delivered = claimed_message_ids(
        consumer="postman",
        claim_type="push_delivered",
        path=claims_path,
        namespace=namespace,
    )

    events: List[Dict[str, Any]] = []
    packet_delivery_count = 0
    command_event_count = 0
    other_event_count = 0
    skipped_status_count = 0
    already_cleared_count = 0

    for message in messages:
        validate_message(message)
        message_id = str(message.get("message_id") or "")
        if message_id in already_cleared:
            already_cleared_count += 1
            continue
        if message.get("status") != "new":
            skipped_status_count += 1
            continue

        kind = message.get("kind")
        if kind == "command":
            event_type = "mailbox.command.queued"
            action = "queued_for_worker"
            command_event_count += 1
        elif kind == "packet" and is_push_ready_packet(message):
            if message_id not in already_delivered:
                deliver_push_packet(
                    message,
                    consumer="postman",
                    inbox_root=inbox_root,
                    operator_root=operator_root,
                    claims_path=claims_path,
                    namespace=namespace,
                )
                already_delivered.add(message_id)
                packet_delivery_count += 1
                event_type = "mailbox.packet.delivered"
                action = "delivered"
            else:
                event_type = "mailbox.packet.already_delivered"
                action = "already_delivered"
        else:
            event_type = "mailbox.message.recorded"
            action = "recorded"
            other_event_count += 1

        event = build_mailbox_clearinghouse_event(
            message,
            event_type=event_type,
            action=action,
            consumer=consumer,
            created_at=created_at,
            inbox_root=inbox_root,
            operator_root=operator_root,
            namespace=namespace,
        )
        append_jsonl(effective_events_path, event)
        append_claim(
            message_id=message_id,
            consumer=consumer,
            claim_type=MAILBOX_CLEARINGHOUSE_CLAIM_TYPE,
            scope={
                "clearinghouse_event_id": event["event_id"],
                "event_type": event["event_type"],
            },
            path=claims_path,
            namespace=namespace,
        )
        already_cleared.add(message_id)
        events.append(event)

    result = {
        "schema_version": MAILBOX_CLEARINGHOUSE_RESULT_SCHEMA_VERSION,
        "clearinghouse_status": "completed",
        "namespace": namespace or MAILBOX_ACTIVE_NAMESPACE,
        "consumer": consumer,
        "event_driven": True,
        "jsonl_storage_only": False,
        "worker_execution_attempted": False,
        "messages_seen": len(messages),
        "events_recorded": len(events),
        "event_ids": [event["event_id"] for event in events],
        "routed_message_ids": [event["message_id"] for event in events],
        "clearinghouse_claims_recorded": len(events),
        "packet_delivery_count": packet_delivery_count,
        "command_event_count": command_event_count,
        "other_event_count": other_event_count,
        "skipped_status_count": skipped_status_count,
        "already_cleared_count": already_cleared_count,
        "claim_type": MAILBOX_CLEARINGHOUSE_CLAIM_TYPE,
        "event_schema_version": MAILBOX_CLEARINGHOUSE_EVENT_SCHEMA_VERSION,
    }
    validate_mailbox_clearinghouse_result(result)
    return result
