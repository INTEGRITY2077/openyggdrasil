from __future__ import annotations

from typing import Any, Dict

from harness_common import DEFAULT_VAULT, EVENTS_PATH, append_jsonl, utc_now_iso


def record_worker_event(event_type: str, payload: Dict[str, Any]) -> None:
    append_jsonl(
        EVENTS_PATH,
        {
            "event_type": event_type,
            "timestamp": utc_now_iso(),
            **payload,
        },
    )


def job_role(job_type: str) -> str:
    from job_registry import get_job_spec

    return get_job_spec(job_type).target_role


def job_capability(job_type: str) -> str:
    from job_registry import get_job_spec

    return get_job_spec(job_type).capability


def job_inference(job_type: str) -> Dict[str, Any]:
    from job_registry import get_job_spec

    return {"mode": get_job_spec(job_type).inference_mode}


def job_scope(job: Dict[str, Any]) -> Dict[str, Any]:
    from job_registry import get_job_spec

    spec = get_job_spec(str(job.get("job_type") or ""))
    payload = job.get("payload", {})
    scope = {
        "vault_path": str(payload.get("vault")) if payload.get("vault") else None,
        "graph_path": str(payload.get("sandbox_root")) if payload.get("sandbox_root") else None,
        "profile": payload.get("profile"),
        "session_id": payload.get("session_id"),
    }
    if spec.write_scope == "vault" and not scope["vault_path"]:
        scope["vault_path"] = str(DEFAULT_VAULT.resolve())
    return scope
