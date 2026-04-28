from __future__ import annotations

import hashlib
import json
import queue
import uuid
import shutil
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
MAILBOX_DB_PATH = MAILBOX_ROOT / "mailbox.sqlite3"
MAILBOX_ACTIVE_NAMESPACE = "active"
QUESTION_INBOX_PREFIX = "question__"
GLOBAL_INBOX_KEY = "global"
SAFE_INBOX_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")
MAILBOX_CLEARINGHOUSE_EVENT_SCHEMA_VERSION = "mailbox_clearinghouse_event.v1"
MAILBOX_CLEARINGHOUSE_RESULT_SCHEMA_VERSION = "mailbox_clearinghouse_result.v1"
MAILBOX_CLEARINGHOUSE_CONSUMER = "mailbox-clearinghouse"
MAILBOX_CLEARINGHOUSE_CLAIM_TYPE = "clearinghouse_event_recorded"
MAILBOX_SQLITE_SCHEMA_VERSION = "mailbox_sqlite_wal_engine.v1"
MAILBOX_WAKEUP_SCHEMA_VERSION = "mailbox_worker_wakeup.v1"
MAILBOX_STATUS_TRANSITION_SCHEMA_VERSION = "mailbox_status_transition.v1"
MAILBOX_JOB_STATUS_TRANSITION_SCHEMA_VERSION = "mailbox_job_status_transition.v1"
MAILBOX_STATUS_STATES = {"accepted", "quarantined", "rejected"}
MAILBOX_JOB_STATUS_STATES = {
    "queued",
    "running",
    "completed",
    "unavailable",
    "failed",
    "timed_out",
    "rejected",
}

_SQLITE_INIT_LOCK = threading.Lock()
_WRITE_QUEUES_LOCK = threading.Lock()
_WRITE_QUEUES: dict[Path, "_MailboxWriteQueue"] = {}
_WAKEUP_SUBSCRIBERS_LOCK = threading.Lock()
_WAKEUP_SUBSCRIBERS: dict[Path, dict[str, list[Callable[[Dict[str, Any]], None]]]] = {}


class _QueuedMailboxWrite:
    def __init__(self, operation: Callable[[sqlite3.Connection], Any]) -> None:
        self.operation = operation
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class _MailboxWriteQueue:
    """Single-writer queue for SQLite WAL mailbox mutations."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._queue: queue.Queue[_QueuedMailboxWrite] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run,
            name=f"mailbox-sqlite-writer-{hashlib.sha1(str(db_path).encode('utf-8')).hexdigest()[:8]}",
            daemon=True,
        )
        self._thread.start()

    def write(self, operation: Callable[[sqlite3.Connection], Any]) -> Any:
        queued = _QueuedMailboxWrite(operation)
        self._queue.put(queued)
        queued.done.wait()
        if queued.error is not None:
            raise queued.error
        return queued.result

    def _run(self) -> None:
        while True:
            queued = self._queue.get()
            try:
                _ensure_mailbox_db(self.db_path)
                with _open_mailbox_db(self.db_path) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    queued.result = queued.operation(connection)
                    connection.commit()
            except BaseException as exc:
                try:
                    connection.rollback()  # type: ignore[name-defined]
                except Exception:
                    pass
                queued.error = exc
            finally:
                queued.done.set()
                self._queue.task_done()


def mailbox_root_for(*, namespace: str | None = None) -> Path:
    normalized = (namespace or "").strip()
    if not normalized or normalized == MAILBOX_ACTIVE_NAMESPACE:
        return MAILBOX_ROOT
    return MAILBOX_NAMESPACE_ROOT / normalized


def mailbox_paths(*, namespace: str | None = None) -> Dict[str, Path]:
    root = mailbox_root_for(namespace=namespace)
    return {
        "root": root,
        "db_path": root / "mailbox.sqlite3",
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


def _effective_db_path(
    *,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> Path:
    return db_path or mailbox_paths(namespace=namespace)["db_path"]


def _open_mailbox_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _ensure_mailbox_db(db_path: Path) -> None:
    with _SQLITE_INIT_LOCK:
        with _open_mailbox_db(db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS mailbox_metadata (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
                INSERT OR REPLACE INTO mailbox_metadata(key, value)
                VALUES ('schema_version', 'mailbox_sqlite_wal_engine.v1');

                CREATE TABLE IF NOT EXISTS mailbox_messages (
                  message_id TEXT PRIMARY KEY,
                  message_type TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  status TEXT NOT NULL,
                  priority TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  message_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mailbox_claims (
                  claim_id TEXT PRIMARY KEY,
                  message_id TEXT NOT NULL,
                  consumer TEXT NOT NULL,
                  claim_type TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  claim_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mailbox_events (
                  event_id TEXT PRIMARY KEY,
                  message_id TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  consumer TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  event_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mailbox_wakeups (
                  wakeup_id TEXT PRIMARY KEY,
                  event_id TEXT NOT NULL,
                  message_id TEXT NOT NULL,
                  consumer TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  wakeup_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mailbox_status_transitions (
                  transition_id TEXT PRIMARY KEY,
                  message_id TEXT NOT NULL,
                  from_state TEXT,
                  to_state TEXT NOT NULL,
                  reason_code TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  transition_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mailbox_job_status_transitions (
                  transition_id TEXT PRIMARY KEY,
                  message_id TEXT NOT NULL,
                  job_id TEXT NOT NULL,
                  lease_request_id TEXT,
                  from_status TEXT,
                  to_status TEXT NOT NULL,
                  reason_code TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  transition_json TEXT NOT NULL
                );
                """
            )


def _write_queue_for(db_path: Path) -> _MailboxWriteQueue:
    resolved = db_path.resolve()
    with _WRITE_QUEUES_LOCK:
        queue_for_path = _WRITE_QUEUES.get(resolved)
        if queue_for_path is None:
            queue_for_path = _MailboxWriteQueue(resolved)
            _WRITE_QUEUES[resolved] = queue_for_path
        return queue_for_path


def _sqlite_write(db_path: Path, operation: Callable[[sqlite3.Connection], Any]) -> Any:
    return _write_queue_for(db_path).write(operation)


def _read_json_rows(db_path: Path, table: str, json_column: str, order_column: str) -> List[Dict[str, Any]]:
    _ensure_mailbox_db(db_path)
    with _open_mailbox_db(db_path) as connection:
        rows = connection.execute(
            f"SELECT {json_column} FROM {table} ORDER BY {order_column}, rowid"
        ).fetchall()
    return [json.loads(str(row[json_column])) for row in rows]


def mailbox_sqlite_engine_status(
    *,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> Dict[str, Any]:
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    _ensure_mailbox_db(effective_db_path)
    with _open_mailbox_db(effective_db_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        counts = {
            "messages": connection.execute("SELECT COUNT(*) FROM mailbox_messages").fetchone()[0],
            "claims": connection.execute("SELECT COUNT(*) FROM mailbox_claims").fetchone()[0],
            "events": connection.execute("SELECT COUNT(*) FROM mailbox_events").fetchone()[0],
            "wakeups": connection.execute("SELECT COUNT(*) FROM mailbox_wakeups").fetchone()[0],
            "status_transitions": connection.execute(
                "SELECT COUNT(*) FROM mailbox_status_transitions"
            ).fetchone()[0],
            "job_status_transitions": connection.execute(
                "SELECT COUNT(*) FROM mailbox_job_status_transitions"
            ).fetchone()[0],
        }
    return {
        "schema_version": MAILBOX_SQLITE_SCHEMA_VERSION,
        "db_path": str(effective_db_path),
        "journal_mode": str(journal_mode).lower(),
        "wal_enabled": str(journal_mode).lower() == "wal",
        "write_queue": "threaded_single_writer",
        "counts": counts,
    }


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
    db_path: Path | None = None,
) -> List[Dict[str, Any]]:
    if path is not None:
        return read_jsonl(path)
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    if effective_db_path.exists():
        return _read_json_rows(effective_db_path, "mailbox_messages", "message_json", "created_at")
    return read_jsonl(mailbox_paths(namespace=namespace)["messages_path"])


def read_claims(
    path: Path | None = None,
    *,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> List[Dict[str, Any]]:
    if path is not None:
        return read_jsonl(path)
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    if effective_db_path.exists():
        return _read_json_rows(effective_db_path, "mailbox_claims", "claim_json", "created_at")
    return read_jsonl(mailbox_paths(namespace=namespace)["claims_path"])


def append_message(
    message: Dict[str, Any],
    *,
    path: Path | None = None,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> Dict[str, Any]:
    ensure_mailbox_dirs(namespace=namespace)
    validate_message(message)
    if path is not None:
        append_jsonl(path, message)
        return message

    ready_message = json_ready(message)
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO mailbox_messages(
              message_id, message_type, kind, status, priority, created_at, message_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ready_message["message_id"],
                ready_message["message_type"],
                ready_message["kind"],
                ready_message["status"],
                ready_message["priority"],
                ready_message["created_at"],
                json.dumps(ready_message, ensure_ascii=False, sort_keys=True),
            ),
        )

    _sqlite_write(effective_db_path, _insert)
    return message


def append_claim(
    *,
    message_id: str,
    consumer: str,
    claim_type: str,
    scope: Optional[Dict[str, Any]] = None,
    path: Path | None = None,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> Dict[str, Any]:
    claim = {
        "claim_id": uuid.uuid4().hex,
        "message_id": message_id,
        "consumer": consumer,
        "claim_type": claim_type,
        "scope": json_ready(scope or {}),
        "created_at": utc_now_iso(),
    }
    if path is not None:
        append_jsonl(path, claim)
        return claim

    ready_claim = json_ready(claim)
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO mailbox_claims(
              claim_id, message_id, consumer, claim_type, created_at, claim_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ready_claim["claim_id"],
                ready_claim["message_id"],
                ready_claim["consumer"],
                ready_claim["claim_type"],
                ready_claim["created_at"],
                json.dumps(ready_claim, ensure_ascii=False, sort_keys=True),
            ),
        )

    _sqlite_write(effective_db_path, _insert)
    return claim


def claimed_message_ids(
    *,
    consumer: Optional[str] = None,
    claim_type: Optional[str] = None,
    path: Path | None = None,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> set[str]:
    claimed: set[str] = set()
    for claim in read_claims(path, namespace=namespace, db_path=db_path):
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
    db_path: Path | None = None,
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
        db_path=db_path,
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
    db_path: Path | None = None,
) -> List[Dict[str, Any]]:
    if path is not None:
        return read_jsonl(path)
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    if effective_db_path.exists():
        return _read_json_rows(effective_db_path, "mailbox_events", "event_json", "created_at")
    return read_jsonl(mailbox_paths(namespace=namespace)["events_path"])


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


def append_mailbox_clearinghouse_event(
    event: Dict[str, Any],
    *,
    path: Path | None = None,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> Dict[str, Any]:
    validate_mailbox_clearinghouse_event(event)
    if path is not None:
        append_jsonl(path, event)
        return event

    ready_event = json_ready(event)
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO mailbox_events(
              event_id, message_id, event_type, consumer, created_at, event_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ready_event["event_id"],
                ready_event["message_id"],
                ready_event["event_type"],
                ready_event["consumer"],
                ready_event["created_at"],
                json.dumps(ready_event, ensure_ascii=False, sort_keys=True),
            ),
        )

    _sqlite_write(effective_db_path, _insert)
    return event


def subscribe_mailbox_wakeup(
    consumer: str,
    callback: Callable[[Dict[str, Any]], None],
    *,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> Dict[str, Any]:
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path).resolve()
    with _WAKEUP_SUBSCRIBERS_LOCK:
        _WAKEUP_SUBSCRIBERS.setdefault(effective_db_path, {}).setdefault(consumer, []).append(callback)
    return {
        "schema_version": "mailbox_wakeup_subscription.v1",
        "consumer": consumer,
        "db_path": str(effective_db_path),
        "subscribed": True,
    }


def _wakeup_consumers_for_event(event: Dict[str, Any]) -> List[str]:
    event_type = str(event.get("event_type") or "")
    if event_type == "mailbox.command.queued":
        return ["reasoning_lease"]
    if event_type == "mailbox.packet.delivered":
        return ["hermes_inbox"]
    return ["mailbox_observer"]


def record_mailbox_wakeup(
    event: Dict[str, Any],
    *,
    consumer: str,
    namespace: str | None = None,
    db_path: Path | None = None,
    created_at: str | None = None,
) -> Dict[str, Any]:
    validate_mailbox_clearinghouse_event(event)
    wakeup = {
        "schema_version": MAILBOX_WAKEUP_SCHEMA_VERSION,
        "wakeup_id": uuid.uuid4().hex,
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "message_id": event["message_id"],
        "consumer": consumer,
        "created_at": created_at or utc_now_iso(),
        "worker_execution_attempted": True,
        "payload_ref": event["payload_ref"],
        "raw_payload_copied": False,
    }
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    ready_wakeup = json_ready(wakeup)

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO mailbox_wakeups(
              wakeup_id, event_id, message_id, consumer, event_type, created_at, wakeup_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ready_wakeup["wakeup_id"],
                ready_wakeup["event_id"],
                ready_wakeup["message_id"],
                ready_wakeup["consumer"],
                ready_wakeup["event_type"],
                ready_wakeup["created_at"],
                json.dumps(ready_wakeup, ensure_ascii=False, sort_keys=True),
            ),
        )

    _sqlite_write(effective_db_path, _insert)
    callbacks: list[Callable[[Dict[str, Any]], None]] = []
    with _WAKEUP_SUBSCRIBERS_LOCK:
        callbacks = list(_WAKEUP_SUBSCRIBERS.get(effective_db_path.resolve(), {}).get(consumer, []))
    for callback in callbacks:
        callback(dict(wakeup))
    return wakeup


def read_mailbox_wakeups(
    *,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> List[Dict[str, Any]]:
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    if not effective_db_path.exists():
        return []
    return _read_json_rows(effective_db_path, "mailbox_wakeups", "wakeup_json", "created_at")


def record_mailbox_status_transition(
    *,
    message_id: str,
    to_state: str,
    from_state: str | None = None,
    reason_code: str,
    namespace: str | None = None,
    db_path: Path | None = None,
    created_at: str | None = None,
) -> Dict[str, Any]:
    if to_state not in MAILBOX_STATUS_STATES:
        raise ValueError(f"Mailbox clearinghouse status must be one of {sorted(MAILBOX_STATUS_STATES)}")
    transition = {
        "schema_version": MAILBOX_STATUS_TRANSITION_SCHEMA_VERSION,
        "transition_id": uuid.uuid4().hex,
        "message_id": message_id,
        "from_state": from_state,
        "to_state": to_state,
        "reason_code": reason_code,
        "created_at": created_at or utc_now_iso(),
    }
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    ready_transition = json_ready(transition)

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO mailbox_status_transitions(
              transition_id, message_id, from_state, to_state, reason_code, created_at, transition_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ready_transition["transition_id"],
                ready_transition["message_id"],
                ready_transition["from_state"],
                ready_transition["to_state"],
                ready_transition["reason_code"],
                ready_transition["created_at"],
                json.dumps(ready_transition, ensure_ascii=False, sort_keys=True),
            ),
        )

    _sqlite_write(effective_db_path, _insert)
    return transition


def read_mailbox_status_transitions(
    *,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> List[Dict[str, Any]]:
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    if not effective_db_path.exists():
        return []
    return _read_json_rows(
        effective_db_path,
        "mailbox_status_transitions",
        "transition_json",
        "created_at",
    )


def record_mailbox_job_status_transition(
    *,
    message_id: str,
    job_id: str,
    to_status: str,
    lease_request_id: str | None = None,
    from_status: str | None = None,
    reason_code: str,
    namespace: str | None = None,
    db_path: Path | None = None,
    created_at: str | None = None,
) -> Dict[str, Any]:
    if to_status not in MAILBOX_JOB_STATUS_STATES:
        raise ValueError(f"Mailbox job status must be one of {sorted(MAILBOX_JOB_STATUS_STATES)}")
    if from_status is not None and from_status not in MAILBOX_JOB_STATUS_STATES:
        raise ValueError(f"Mailbox job previous status must be one of {sorted(MAILBOX_JOB_STATUS_STATES)}")
    transition = {
        "schema_version": MAILBOX_JOB_STATUS_TRANSITION_SCHEMA_VERSION,
        "transition_id": uuid.uuid4().hex,
        "message_id": message_id,
        "job_id": job_id,
        "lease_request_id": lease_request_id,
        "from_status": from_status,
        "to_status": to_status,
        "reason_code": reason_code,
        "created_at": created_at or utc_now_iso(),
    }
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    ready_transition = json_ready(transition)

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO mailbox_job_status_transitions(
              transition_id, message_id, job_id, lease_request_id, from_status,
              to_status, reason_code, created_at, transition_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ready_transition["transition_id"],
                ready_transition["message_id"],
                ready_transition["job_id"],
                ready_transition["lease_request_id"],
                ready_transition["from_status"],
                ready_transition["to_status"],
                ready_transition["reason_code"],
                ready_transition["created_at"],
                json.dumps(ready_transition, ensure_ascii=False, sort_keys=True),
            ),
        )

    _sqlite_write(effective_db_path, _insert)
    return transition


def read_mailbox_job_status_transitions(
    *,
    namespace: str | None = None,
    db_path: Path | None = None,
) -> List[Dict[str, Any]]:
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    if not effective_db_path.exists():
        return []
    return _read_json_rows(
        effective_db_path,
        "mailbox_job_status_transitions",
        "transition_json",
        "created_at",
    )


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
    db_path: Path | None = None,
    consumer: str = MAILBOX_CLEARINGHOUSE_CONSUMER,
    created_at: str | None = None,
    wakeup_consumers: List[str] | None = None,
) -> Dict[str, Any]:
    ensure_mailbox_dirs(namespace=namespace)
    paths = mailbox_paths(namespace=namespace)
    effective_events_path = events_path or paths["events_path"]
    effective_db_path = _effective_db_path(namespace=namespace, db_path=db_path)
    sqlite_mode = messages_path is None and claims_path is None and events_path is None
    messages = read_messages(messages_path, namespace=namespace, db_path=effective_db_path)
    already_cleared = claimed_message_ids(
        consumer=consumer,
        claim_type=MAILBOX_CLEARINGHOUSE_CLAIM_TYPE,
        path=claims_path,
        namespace=namespace,
        db_path=effective_db_path,
    )
    already_delivered = claimed_message_ids(
        consumer="postman",
        claim_type="push_delivered",
        path=claims_path,
        namespace=namespace,
        db_path=effective_db_path,
    )

    events: List[Dict[str, Any]] = []
    packet_delivery_count = 0
    command_event_count = 0
    other_event_count = 0
    skipped_status_count = 0
    already_cleared_count = 0
    wakeups_recorded = 0
    status_transitions_recorded = 0

    for message in messages:
        validate_message(message)
        message_id = str(message.get("message_id") or "")
        if message_id in already_cleared:
            already_cleared_count += 1
            continue
        if message.get("status") != "new":
            skipped_status_count += 1
            if sqlite_mode:
                record_mailbox_status_transition(
                    message_id=message_id,
                    from_state=str(message.get("status")),
                    to_state="quarantined",
                    reason_code="message_status_not_new",
                    namespace=namespace,
                    db_path=effective_db_path,
                    created_at=created_at,
                )
                status_transitions_recorded += 1
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
                    db_path=effective_db_path,
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
        append_mailbox_clearinghouse_event(
            event,
            path=effective_events_path if events_path is not None else None,
            namespace=namespace,
            db_path=effective_db_path,
        )
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
            db_path=effective_db_path,
        )
        if sqlite_mode:
            record_mailbox_status_transition(
                message_id=message_id,
                from_state="new",
                to_state="accepted",
                reason_code=event_type,
                namespace=namespace,
                db_path=effective_db_path,
                created_at=created_at,
            )
            status_transitions_recorded += 1
            for wakeup_consumer in (wakeup_consumers or _wakeup_consumers_for_event(event)):
                record_mailbox_wakeup(
                    event,
                    consumer=wakeup_consumer,
                    namespace=namespace,
                    db_path=effective_db_path,
                    created_at=created_at,
                )
                wakeups_recorded += 1
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
        "sqlite_wal_engine": sqlite_mode,
        "sqlite_db_path": str(effective_db_path) if sqlite_mode else None,
        "event_ids": [event["event_id"] for event in events],
        "routed_message_ids": [event["message_id"] for event in events],
        "clearinghouse_claims_recorded": len(events),
        "wakeups_recorded": wakeups_recorded,
        "status_transitions_recorded": status_transitions_recorded,
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
