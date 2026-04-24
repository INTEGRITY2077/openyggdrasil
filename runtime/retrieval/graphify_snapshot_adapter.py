from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from harness_common import utc_now_iso


DERIVED_SOURCE_ROLE = "derived_graph_snapshot"
CANONICALITY = "non_sot"
MUTATION_POLICY = "read_only_no_sot_mutation"
FORBIDDEN_OPERATIONS = [
    "write_vault",
    "write_sot",
    "rewrite_provider_raw_session",
    "treat_graphify_as_canonical",
]
ALLOWED_OPERATIONS = [
    "read_graphify_summary",
    "read_graphify_graph",
    "read_manifest",
    "emit_derived_snapshot_hint",
]
REQUIRED_SUMMARY_KEYS = ("nodes", "edges", "communities")


def _non_negative_int(value: Any, *, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Graphify summary field must be a non-negative integer: {key}")
    return value


def normalize_graphify_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {
        "nodes": _non_negative_int(summary.get("nodes"), key="nodes"),
        "edges": _non_negative_int(summary.get("edges"), key="edges"),
        "communities": _non_negative_int(summary.get("communities"), key="communities"),
        "god_nodes": list(summary.get("god_nodes") or []),
        "surprising_connections": list(summary.get("surprising_connections") or []),
    }
    return normalized


def read_graphify_summary(summary_path: Path) -> dict[str, Any]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Graphify summary must be a JSON object")
    return normalize_graphify_summary(payload)


def build_graphify_snapshot_adapter_payload(
    *,
    graph_path: Path,
    summary_path: Path,
    manifest_path: Path | None,
    vault_root: Path,
    summary: Mapping[str, Any],
    freshness: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "graphify_snapshot_adapter.v1",
        "status": "available",
        "source_role": DERIVED_SOURCE_ROLE,
        "canonicality": CANONICALITY,
        "mutation_policy": MUTATION_POLICY,
        "allowed_operations": list(ALLOWED_OPERATIONS),
        "forbidden_operations": list(FORBIDDEN_OPERATIONS),
        "graph_path": str(graph_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "vault_root": str(vault_root),
        "summary": normalize_graphify_summary(summary),
        "freshness": dict(freshness or {}),
        "failure": None,
        "generated_at": generated_at or utc_now_iso(),
    }
    validate_graphify_snapshot_adapter_payload(payload)
    return payload


def build_graphify_snapshot_failure_payload(
    *,
    graph_path: Path | None,
    summary_path: Path | None,
    manifest_path: Path | None,
    vault_root: Path,
    reason_code: str,
    message: str,
    freshness: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "graphify_snapshot_adapter.v1",
        "status": "unavailable",
        "source_role": DERIVED_SOURCE_ROLE,
        "canonicality": CANONICALITY,
        "mutation_policy": MUTATION_POLICY,
        "allowed_operations": list(ALLOWED_OPERATIONS),
        "forbidden_operations": list(FORBIDDEN_OPERATIONS),
        "graph_path": str(graph_path) if graph_path else None,
        "summary_path": str(summary_path) if summary_path else None,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "vault_root": str(vault_root),
        "summary": None,
        "freshness": dict(freshness or {}),
        "failure": {
            "reason_code": reason_code,
            "message": message,
        },
        "generated_at": generated_at or utc_now_iso(),
    }
    validate_graphify_snapshot_adapter_payload(payload)
    return payload


def adapt_graphify_snapshot(
    *,
    graph_path: Path,
    summary_path: Path,
    manifest_path: Path | None,
    vault_root: Path,
    freshness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        summary = read_graphify_summary(summary_path)
    except Exception as exc:
        return build_graphify_snapshot_failure_payload(
            graph_path=graph_path,
            summary_path=summary_path,
            manifest_path=manifest_path,
            vault_root=vault_root,
            reason_code="graphify_summary_unreadable",
            message=str(exc),
            freshness=freshness,
        )
    if not graph_path.exists():
        return build_graphify_snapshot_failure_payload(
            graph_path=graph_path,
            summary_path=summary_path,
            manifest_path=manifest_path,
            vault_root=vault_root,
            reason_code="graphify_graph_missing",
            message=f"Missing graph file: {graph_path}",
            freshness=freshness,
        )
    return build_graphify_snapshot_adapter_payload(
        graph_path=graph_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        vault_root=vault_root,
        summary=summary,
        freshness=freshness,
    )


def validate_graphify_snapshot_adapter_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "graphify_snapshot_adapter.v1":
        raise ValueError("Invalid graphify snapshot adapter schema_version")
    if payload.get("source_role") != DERIVED_SOURCE_ROLE:
        raise ValueError("Graphify snapshot must remain a derived graph snapshot")
    if payload.get("canonicality") != CANONICALITY:
        raise ValueError("Graphify snapshot must not be marked canonical")
    if payload.get("mutation_policy") != MUTATION_POLICY:
        raise ValueError("Graphify snapshot adapter must be read-only")
    allowed = set(payload.get("allowed_operations") or [])
    forbidden = set(payload.get("forbidden_operations") or [])
    if forbidden != set(FORBIDDEN_OPERATIONS):
        raise ValueError("Graphify snapshot adapter forbidden operations changed")
    if allowed & forbidden:
        raise ValueError("Graphify snapshot adapter allowed operations overlap forbidden operations")
    if payload.get("status") == "available":
        if payload.get("failure") is not None:
            raise ValueError("Available Graphify snapshot must not carry failure")
        summary = payload.get("summary")
        if not isinstance(summary, Mapping):
            raise ValueError("Available Graphify snapshot requires summary")
        normalize_graphify_summary(summary)
    elif payload.get("status") == "unavailable":
        failure = payload.get("failure")
        if not isinstance(failure, Mapping) or not failure.get("reason_code"):
            raise ValueError("Unavailable Graphify snapshot requires failure reason_code")
        if payload.get("summary") is not None:
            raise ValueError("Unavailable Graphify snapshot must not carry summary")
    else:
        raise ValueError("Graphify snapshot adapter status must be available or unavailable")
