from __future__ import annotations

import uuid
import shutil
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from delivery.mailbox_schema import validate_message
from harness_common import OPS_ROOT, append_jsonl, json_ready, read_jsonl, utc_now_iso


MAILBOX_ROOT = OPS_ROOT / "mailbox"
MAILBOX_MESSAGES_PATH = MAILBOX_ROOT / "messages.jsonl"
MAILBOX_CLAIMS_PATH = MAILBOX_ROOT / "claims.jsonl"
MAILBOX_INBOX_ROOT = MAILBOX_ROOT / "inbox"
MAILBOX_OPERATOR_ROOT = MAILBOX_ROOT / "operator"
MAILBOX_NAMESPACE_ROOT = MAILBOX_ROOT / "namespaces"
MAILBOX_ARCHIVE_ROOT = MAILBOX_ROOT / "archive"
MAILBOX_ACTIVE_NAMESPACE = "active"
QUESTION_INBOX_PREFIX = "question__"
GLOBAL_INBOX_KEY = "global"
SAFE_INBOX_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


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
