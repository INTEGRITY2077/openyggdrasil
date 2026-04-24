from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping

from graph_builder import execute_graph_rebuild
from sot_writer import execute_promotion


JobHandler = Callable[[Dict[str, Any]], Dict[str, Any]]
@dataclass(frozen=True)
class JobSpec:
    job_type: str
    capability: str
    target_role: str
    inference_mode: str
    write_scope: str
    handler: JobHandler


JOB_REGISTRY: Dict[str, JobSpec] = {
    "promotion": JobSpec(
        job_type="promotion",
        capability="ingest",
        target_role="sot_writer",
        inference_mode="deterministic",
        write_scope="vault",
        handler=execute_promotion,
    ),
    "graph_rebuild": JobSpec(
        job_type="graph_rebuild",
        capability="query",
        target_role="graph_builder",
        inference_mode="hermes_runtime",
        write_scope="graph",
        handler=execute_graph_rebuild,
    ),
}


def get_job_spec(job_type: str) -> JobSpec:
    try:
        return JOB_REGISTRY[job_type]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported job type: {job_type}") from exc


def get_job_handler(job_type: str) -> JobHandler:
    return get_job_spec(job_type).handler


def resolve_job_spec(job_type: str, *, registry: Mapping[str, JobSpec] | None = None) -> JobSpec:
    return (registry or JOB_REGISTRY).get(job_type) or get_job_spec(job_type)
