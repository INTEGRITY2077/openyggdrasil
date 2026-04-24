from __future__ import annotations

import json
import os
import shutil
import socket
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


OPENYGGDRASIL_ROOT = Path(
    os.getenv("OPENYGGDRASIL_ROOT", str(Path(__file__).resolve().parents[1]))
)
CORE_ROOT = OPENYGGDRASIL_ROOT
WORKSPACE_ROOT = Path(
    os.getenv("OPENYGGDRASIL_WORKSPACE_ROOT", str(OPENYGGDRASIL_ROOT))
)
WORKSPACE_RUNTIME_ROOT = WORKSPACE_ROOT / ".yggdrasil"
PROVIDER_ROOT = Path(
    os.getenv(
        "HERMES_ROOT",
        os.getenv("HERMES_ROUTER_ROOT", str(OPENYGGDRASIL_ROOT / "providers" / "hermes")),
    )
)
CENTRAL_ROOT = PROVIDER_ROOT
LEGACY_OPS_ROOT = PROVIDER_ROOT / "ops"
DEFAULT_RUNTIME_STATE_ROOT = WORKSPACE_RUNTIME_ROOT / "ops"
RUNTIME_STATE_ROOT = Path(
    os.getenv(
        "OPENYGGDRASIL_RUNTIME_STATE_ROOT",
        os.getenv("OPENYGGDRASIL_OPS_ROOT", str(DEFAULT_RUNTIME_STATE_ROOT)),
    )
)
OPS_ROOT = RUNTIME_STATE_ROOT
QUEUE_ROOT = OPS_ROOT / "queue"
LOCKS_ROOT = OPS_ROOT / "locks"
HERMES_HOME_WIN = Path(os.getenv("HERMES_HOME_WIN", str(Path.home() / ".hermes")))
HERMES_HOME_POSIX = os.getenv("HERMES_HOME", "~/.hermes").rstrip("/")
DEFAULT_HERMES_BIN = os.getenv("HERMES_BIN", "hermes")

JOBS_PATH = QUEUE_ROOT / "jobs.jsonl"
EVENTS_PATH = QUEUE_ROOT / "worker-events.jsonl"

DEFAULT_GRAPHIFY_SANDBOX = Path(
    os.getenv("GRAPHIFY_SANDBOX_ROOT", str(OPENYGGDRASIL_ROOT / ".runtime" / "graphify-poc"))
)
DEFAULT_GRAPHIFY_MANIFEST = (
    Path(
        os.getenv(
            "GRAPHIFY_MANIFEST_PATH",
            str(OPENYGGDRASIL_ROOT / "projects" / "graphify-poc" / "graphify-corpus.manifest.json"),
        )
    )
)
DEFAULT_VAULT = Path(
    os.getenv(
        "OPENYGGDRASIL_VAULT_ROOT",
        os.getenv("HERMES_VAULT_ROOT", str(OPENYGGDRASIL_ROOT / "vault")),
    )
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hermes_profile_home_win(profile: str) -> Path:
    if profile == "default":
        return HERMES_HOME_WIN
    return HERMES_HOME_WIN / "profiles" / profile


def hermes_state_db_posix(profile: str) -> str:
    if profile == "default":
        return f"{HERMES_HOME_POSIX}/state.db"
    return f"{HERMES_HOME_POSIX}/profiles/{profile}/state.db"


def _should_seed_runtime_state_from_legacy() -> bool:
    return (
        OPS_ROOT == DEFAULT_RUNTIME_STATE_ROOT
        and OPS_ROOT != LEGACY_OPS_ROOT
        and not OPS_ROOT.exists()
        and LEGACY_OPS_ROOT.exists()
    )


def ensure_runtime_state_root() -> None:
    OPS_ROOT.parent.mkdir(parents=True, exist_ok=True)
    if _should_seed_runtime_state_from_legacy():
        shutil.copytree(LEGACY_OPS_ROOT, OPS_ROOT, dirs_exist_ok=True)
    OPS_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_runtime_dirs() -> None:
    ensure_runtime_state_root()
    QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    LOCKS_ROOT.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def record_event(event_type: str, payload: Dict[str, Any]) -> None:
    ensure_runtime_dirs()
    append_jsonl(
        EVENTS_PATH,
        {
            "event_type": event_type,
            "timestamp": utc_now_iso(),
            **payload,
        },
    )


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


def build_job(
    job_type: str,
    payload: Dict[str, Any],
    requested_by: str,
    *,
    parent_question_id: str | None = None,
) -> Dict[str, Any]:
    normalized_payload = json_ready(payload)
    job_id = uuid.uuid4().hex
    return {
        "job_id": job_id,
        "job_type": job_type,
        "payload": normalized_payload,
        "job_key": job_key_for(job_type, normalized_payload),
        "requested_by": requested_by,
        "parent_question_id": parent_question_id,
        "created_at": utc_now_iso(),
        "replay_root_job_id": job_id,
        "replay_depth": 0,
    }


def enqueue_job(job: Dict[str, Any]) -> Dict[str, Any]:
    ensure_runtime_dirs()
    append_jsonl(JOBS_PATH, job)
    append_jsonl(
        EVENTS_PATH,
        {
            "event_type": "job_enqueued",
            "job_id": job["job_id"],
            "job_type": job["job_type"],
            "job_key": job.get("job_key"),
            "parent_question_id": job.get("parent_question_id"),
            "created_at": job["created_at"],
        },
    )
    return job


def completed_statuses() -> Dict[str, str]:
    statuses: Dict[str, str] = {}
    for event in read_jsonl(EVENTS_PATH):
        if event.get("event_type") == "job_succeeded":
            statuses[event["job_id"]] = "succeeded"
        elif event.get("event_type") == "job_failed":
            statuses[event["job_id"]] = "failed"
    return statuses


def queued_jobs() -> List[Dict[str, Any]]:
    statuses = completed_statuses()
    return [job for job in read_jsonl(JOBS_PATH) if job["job_id"] not in statuses]


def job_key_for(job_type: str, payload: Dict[str, Any]) -> str:
    canonical = json.dumps({"job_type": job_type, "payload": payload}, sort_keys=True, ensure_ascii=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def all_jobs() -> List[Dict[str, Any]]:
    return read_jsonl(JOBS_PATH)


def find_job(job_id: str) -> Optional[Dict[str, Any]]:
    for job in all_jobs():
        if job.get("job_id") == job_id:
            return job
    return None


def latest_event_index() -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for event in read_jsonl(EVENTS_PATH):
        job_id = event.get("job_id")
        if not job_id:
            continue
        latest[job_id] = event
    return latest


def active_job_for_key(job_key: str) -> Optional[Dict[str, Any]]:
    statuses = completed_statuses()
    for job in reversed(all_jobs()):
        if job.get("job_key") != job_key:
            continue
        if job.get("job_id") not in statuses:
            return job
    return None


def failed_jobs() -> List[Dict[str, Any]]:
    jobs_by_id = {job["job_id"]: job for job in all_jobs()}
    failures: List[Dict[str, Any]] = []
    for event in read_jsonl(EVENTS_PATH):
        if event.get("event_type") != "job_failed":
            continue
        job = jobs_by_id.get(event.get("job_id"))
        if not job:
            continue
        failures.append(
            {
                "job": job,
                "event": event,
            }
        )
    return failures


@contextmanager
def file_lock(name: str) -> Iterator[Path]:
    ensure_runtime_dirs()
    path = LOCKS_ROOT / f"{name}.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(path), flags)
    metadata = {
        "lock": name,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "created_at": utc_now_iso(),
    }
    os.write(fd, json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
    try:
        yield path
    finally:
        try:
            os.close(fd)
        finally:
            if path.exists():
                path.unlink()


@contextmanager
def retrying_file_lock(
    name: str,
    *,
    timeout_seconds: float = 10.0,
    poll_interval: float = 0.1,
) -> Iterator[Path]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with file_lock(name) as lock_path:
                yield lock_path
                return
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for lock: {name}")
            time.sleep(poll_interval)


ensure_runtime_state_root()
