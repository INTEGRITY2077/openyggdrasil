from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Set

from harness_common import find_job, latest_event_index


DEFAULT_MAX_REPLAY_DEPTH = 2


@dataclass(frozen=True)
class ReplayLineage:
    replay_root_job_id: str
    current_depth: int
    next_depth: int
    parent_question_id: str | None


def latest_job_status(job_id: str, *, event_index: Mapping[str, Dict[str, Any]] | None = None) -> str:
    latest = (event_index or latest_event_index()).get(job_id)
    event_type = str((latest or {}).get("event_type") or "")
    if event_type == "job_failed":
        return "failed"
    if event_type == "job_succeeded":
        return "succeeded"
    if event_type == "job_started":
        return "running"
    if event_type == "job_enqueued":
        return "queued"
    if not latest:
        return "unknown"
    return event_type


def replay_root_job_id(job: Mapping[str, Any]) -> str:
    root = str(job.get("replay_root_job_id") or "").strip()
    if root:
        return root
    return _walk_replay_root(job, seen=set())


def replay_depth(job: Mapping[str, Any]) -> int:
    value = job.get("replay_depth")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return _walk_replay_depth(job, seen=set())


def ensure_job_replayable(
    job: Mapping[str, Any],
    *,
    max_replay_depth: int = DEFAULT_MAX_REPLAY_DEPTH,
    event_index: Mapping[str, Dict[str, Any]] | None = None,
) -> ReplayLineage:
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        raise RuntimeError("Replay candidate is missing job_id")

    status = latest_job_status(job_id, event_index=event_index)
    if status != "failed":
        raise RuntimeError(
            f"Job '{job_id}' is not replayable because latest status is '{status}', not 'failed'"
        )

    current_depth = replay_depth(job)
    if current_depth >= max_replay_depth:
        raise RuntimeError(
            f"Replay depth limit reached for job '{job_id}': current depth {current_depth}, max {max_replay_depth}"
        )

    return ReplayLineage(
        replay_root_job_id=replay_root_job_id(job),
        current_depth=current_depth,
        next_depth=current_depth + 1,
        parent_question_id=_parent_question_id(job),
    )


def apply_replay_lineage(job: MutableMapping[str, Any], *, source_job: Mapping[str, Any], lineage: ReplayLineage) -> MutableMapping[str, Any]:
    job["replayed_from"] = source_job["job_id"]
    job["replay_root_job_id"] = lineage.replay_root_job_id
    job["replay_depth"] = lineage.next_depth
    if lineage.parent_question_id:
        job["parent_question_id"] = lineage.parent_question_id
    return job


def _walk_replay_root(job: Mapping[str, Any], *, seen: Set[str]) -> str:
    job_id = str(job.get("job_id") or "").strip()
    replayed_from = str(job.get("replayed_from") or "").strip()
    if not replayed_from:
        return job_id
    if replayed_from in seen:
        raise RuntimeError(f"Replay lineage cycle detected at '{replayed_from}'")
    seen.add(replayed_from)
    parent = find_job(replayed_from)
    if not parent:
        return replayed_from
    parent_root = str(parent.get("replay_root_job_id") or "").strip()
    if parent_root:
        return parent_root
    return _walk_replay_root(parent, seen=seen)


def _walk_replay_depth(job: Mapping[str, Any], *, seen: Set[str]) -> int:
    replayed_from = str(job.get("replayed_from") or "").strip()
    if not replayed_from:
        return 0
    if replayed_from in seen:
        raise RuntimeError(f"Replay lineage cycle detected at '{replayed_from}'")
    seen.add(replayed_from)
    parent = find_job(replayed_from)
    if not parent:
        return 1
    parent_depth = parent.get("replay_depth")
    if isinstance(parent_depth, int):
        return parent_depth + 1
    if isinstance(parent_depth, str) and parent_depth.strip():
        return int(parent_depth) + 1
    return _walk_replay_depth(parent, seen=seen) + 1


def _parent_question_id(job: Mapping[str, Any]) -> str | None:
    value = str(job.get("parent_question_id") or "").strip()
    if value:
        return value
    replayed_from = str(job.get("replayed_from") or "").strip()
    if not replayed_from:
        return None
    parent = find_job(replayed_from)
    if not parent:
        return None
    return _parent_question_id(parent)
