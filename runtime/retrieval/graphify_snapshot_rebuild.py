from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from retrieval.graphify_snapshot_adapter import (
    build_graphify_snapshot_failure_payload,
    validate_graphify_snapshot_adapter_payload,
)
from retrieval.graphify_snapshot_manifest import (
    build_graphify_snapshot_manifest,
    validate_graphify_snapshot_manifest,
)


SCHEMA_VERSION = "graphify_snapshot_rebuild_result.v1"
INCREMENTAL_MANIFEST_SCHEMA_VERSION = "graphify_incremental_manifest.v1"
SOURCE_ROLE = "derived_graph_snapshot_rebuild"
INCREMENTAL_SOURCE_ROLE = "derived_graph_incremental_manifest"
CANONICALITY = "non_sot"
MUTATION_POLICY = "read_only_no_sot_mutation"
EXECUTION_POLICY = "external_graphify_optional_typed_unavailable"
DEFAULT_INPUT_DIR_NAME = "input-wiki-small"
DEFAULT_OUTPUT_DIR_NAME = "graphify-out"


def graphify_rebuild_paths(
    *,
    sandbox_root: Path,
    input_dir: Path | None = None,
) -> dict[str, Path]:
    resolved_sandbox = sandbox_root.resolve()
    resolved_input = (input_dir or (resolved_sandbox / DEFAULT_INPUT_DIR_NAME)).resolve()
    output_dir = resolved_sandbox / DEFAULT_OUTPUT_DIR_NAME
    return {
        "sandbox_root": resolved_sandbox,
        "input_dir": resolved_input,
        "output_dir": output_dir,
        "graph_path": output_dir / "graph.json",
        "summary_path": output_dir / "summary.json",
        "report_path": output_dir / "GRAPH_REPORT.md",
        "html_path": output_dir / "graph.html",
    }


def build_graphify_rebuild_command(
    *,
    vault_root: Path,
    sandbox_root: Path,
    corpus_manifest_path: Path | None,
    input_dir: Path | None = None,
) -> list[str]:
    command = [
        "py",
        "-3",
        "common/graphify/run_graphify_pipeline.py",
        "--vault",
        str(vault_root),
        "--sandbox-root",
        str(sandbox_root),
    ]
    if input_dir is not None:
        command.extend(["--input-dir", str(input_dir)])
    if corpus_manifest_path is not None:
        command.extend(["--manifest", str(corpus_manifest_path)])
    return command


def _input_boundary(
    *,
    vault_root: Path,
    sandbox_root: Path,
    corpus_manifest_path: Path | None,
    input_dir: Path,
    rebuild_command: list[str],
) -> dict[str, Any]:
    return {
        "vault_root": str(vault_root),
        "sandbox_root": str(sandbox_root),
        "input_dir": str(input_dir),
        "corpus_manifest_path": str(corpus_manifest_path) if corpus_manifest_path else None,
        "allowed_input_roles": [
            "canonical_vault_markdown",
            "graphify_corpus_manifest",
            "derived_staging_input",
        ],
        "forbidden_input_roles": [
            "provider_raw_session",
            "provider_raw_transcript",
            "canonical_vault_mutation",
        ],
        "rebuild_command": list(rebuild_command),
    }


def _output_boundary(paths: Mapping[str, Path]) -> dict[str, Any]:
    return {
        "graph_path": str(paths["graph_path"]),
        "summary_path": str(paths["summary_path"]),
        "report_path": str(paths["report_path"]),
        "html_path": str(paths["html_path"]),
        "output_role": "derived_navigation_and_reporting_only",
        "canonical_output_allowed": False,
    }


def _safety() -> dict[str, bool]:
    return {
        "graphify_is_sot": False,
        "must_verify_against_sot": True,
        "provider_may_answer_from_graphify_alone": False,
        "raw_session_copy_allowed": False,
        "raw_transcript_copy_allowed": False,
        "vault_write_allowed": False,
        "provider_raw_session_copied": False,
        "doc_committed": False,
    }


def _incremental_provenance_policy() -> dict[str, bool]:
    return {
        "graphify_is_sot": False,
        "must_verify_against_sot": True,
        "provider_may_answer_from_graphify_alone": False,
        "raw_session_copy_allowed": False,
        "raw_transcript_copy_allowed": False,
        "vault_write_allowed": False,
    }


def _safe_refs(values: Sequence[str] | None) -> list[str]:
    refs = [str(value).strip() for value in (values or []) if str(value).strip()]
    forbidden_prefixes = ("D:/", "D:\\", "C:/", "C:\\", "file://")
    forbidden_fragments = ("transcript", "credential", "secret", "api_key", "apikey", ".env")
    for ref in refs:
        normalized = ref.lower().replace("\\", "/")
        if normalized.startswith(tuple(prefix.lower().replace("\\", "/") for prefix in forbidden_prefixes)):
            raise ValueError(f"Graphify incremental manifest ref is not portable: {ref}")
        if any(fragment in normalized for fragment in forbidden_fragments):
            raise ValueError(f"Graphify incremental manifest ref contains forbidden material: {ref}")
    return refs


def build_graphify_incremental_manifest(
    *,
    previous_snapshot_manifest: Mapping[str, Any],
    current_snapshot_manifest: Mapping[str, Any],
    changed_input_refs: Sequence[str] | None = None,
    unchanged_input_refs: Sequence[str] | None = None,
    removed_input_refs: Sequence[str] | None = None,
    manifest_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_graphify_snapshot_manifest(previous_snapshot_manifest)
    validate_graphify_snapshot_manifest(current_snapshot_manifest)
    changed_refs = _safe_refs(changed_input_refs)
    unchanged_refs = _safe_refs(unchanged_input_refs)
    removed_refs = _safe_refs(removed_input_refs)
    status = str(current_snapshot_manifest.get("status") or "unavailable")
    delta_applied = status == "available"
    failure = None
    if not delta_applied:
        reason = "current_snapshot_unavailable"
        message = "Current Graphify snapshot is unavailable; incremental delta is recorded but not applied."
        failure = {
            "reason_code": reason,
            "message": message,
        }
    payload = {
        "schema_version": INCREMENTAL_MANIFEST_SCHEMA_VERSION,
        "manifest_id": manifest_id or f"graphify-incremental:{uuid.uuid4().hex}",
        "source_role": INCREMENTAL_SOURCE_ROLE,
        "status": status,
        "canonicality": CANONICALITY,
        "mutation_policy": MUTATION_POLICY,
        "incremental_mode": "delta_manifest",
        "previous_snapshot_manifest_id": str(previous_snapshot_manifest.get("manifest_id") or ""),
        "current_snapshot_manifest_id": str(current_snapshot_manifest.get("manifest_id") or ""),
        "previous_snapshot_status": str(previous_snapshot_manifest.get("status") or ""),
        "current_snapshot_status": status,
        "delta": {
            "changed_input_refs": changed_refs,
            "unchanged_input_refs": unchanged_refs,
            "removed_input_refs": removed_refs,
            "changed_count": len(changed_refs),
            "unchanged_count": len(unchanged_refs),
            "removed_count": len(removed_refs),
            "delta_applied": delta_applied,
        },
        "provenance_policy": _incremental_provenance_policy(),
        "failure": failure,
        "generated_at": generated_at or utc_now_iso(),
    }
    validate_graphify_incremental_manifest(payload)
    return payload


def validate_graphify_incremental_manifest(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != INCREMENTAL_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Invalid Graphify incremental manifest schema_version")
    if payload.get("source_role") != INCREMENTAL_SOURCE_ROLE:
        raise ValueError("Graphify incremental manifest must remain a derived manifest")
    if payload.get("canonicality") != CANONICALITY:
        raise ValueError("Graphify incremental manifest must remain non-SOT")
    if payload.get("mutation_policy") != MUTATION_POLICY:
        raise ValueError("Graphify incremental manifest must be read-only")
    if payload.get("incremental_mode") != "delta_manifest":
        raise ValueError("Graphify incremental manifest requires delta_manifest mode")
    for key in ("manifest_id", "previous_snapshot_manifest_id", "current_snapshot_manifest_id", "generated_at"):
        if not str(payload.get(key) or "").strip():
            raise ValueError(f"Graphify incremental manifest requires {key}")

    policy = payload.get("provenance_policy")
    if not isinstance(policy, Mapping):
        raise ValueError("Graphify incremental manifest requires provenance_policy")
    if policy.get("graphify_is_sot") is not False:
        raise ValueError("Graphify incremental manifest must remain non-SOT")
    if policy.get("must_verify_against_sot") is not True:
        raise ValueError("Graphify incremental manifest must require SOT verification")
    for flag in (
        "provider_may_answer_from_graphify_alone",
        "raw_session_copy_allowed",
        "raw_transcript_copy_allowed",
        "vault_write_allowed",
    ):
        if policy.get(flag) is not False:
            raise ValueError(f"Graphify incremental manifest safety flag must be false: {flag}")

    delta = payload.get("delta")
    if not isinstance(delta, Mapping):
        raise ValueError("Graphify incremental manifest requires delta")
    changed = _safe_refs(delta.get("changed_input_refs") if isinstance(delta.get("changed_input_refs"), list) else [])
    unchanged = _safe_refs(delta.get("unchanged_input_refs") if isinstance(delta.get("unchanged_input_refs"), list) else [])
    removed = _safe_refs(delta.get("removed_input_refs") if isinstance(delta.get("removed_input_refs"), list) else [])
    if delta.get("changed_count") != len(changed):
        raise ValueError("Graphify incremental manifest changed_count mismatch")
    if delta.get("unchanged_count") != len(unchanged):
        raise ValueError("Graphify incremental manifest unchanged_count mismatch")
    if delta.get("removed_count") != len(removed):
        raise ValueError("Graphify incremental manifest removed_count mismatch")

    status = payload.get("status")
    if status == "available":
        if delta.get("delta_applied") is not True:
            raise ValueError("Available Graphify incremental manifest must apply delta")
        if payload.get("failure") is not None:
            raise ValueError("Available Graphify incremental manifest must not carry failure")
    elif status == "unavailable":
        if delta.get("delta_applied") is not False:
            raise ValueError("Unavailable Graphify incremental manifest must not apply delta")
        failure = payload.get("failure")
        if not isinstance(failure, Mapping) or not failure.get("reason_code"):
            raise ValueError("Unavailable Graphify incremental manifest requires failure")
    else:
        raise ValueError("Graphify incremental manifest status must be available or unavailable")

    for forbidden_key in ("graph_path", "summary_path", "vault_root", "payload"):
        if forbidden_key in payload:
            raise ValueError(f"Graphify incremental manifest must be path-free: {forbidden_key}")
    serialized = str(dict(payload)).replace("\\", "/").lower()
    if "d:/" in serialized or "c:/" in serialized or "file://" in serialized:
        raise ValueError("Graphify incremental manifest must not include local filesystem paths")


def _existing_output_failure(paths: Mapping[str, Path]) -> tuple[str, str] | None:
    graph_exists = paths["graph_path"].exists()
    summary_exists = paths["summary_path"].exists()
    if graph_exists and summary_exists:
        return None
    if not graph_exists and not summary_exists:
        return (
            "graphify_snapshot_outputs_missing",
            f"Missing graph and summary outputs: {paths['graph_path']}; {paths['summary_path']}",
        )
    if not graph_exists:
        return ("graphify_graph_missing", f"Missing graph file: {paths['graph_path']}")
    return ("graphify_summary_missing", f"Missing summary file: {paths['summary_path']}")


def build_graphify_snapshot_rebuild_result(
    *,
    vault_root: Path,
    sandbox_root: Path,
    corpus_manifest_path: Path | None,
    input_dir: Path | None = None,
    freshness: Mapping[str, Any] | None = None,
    previous_snapshot_manifest: Mapping[str, Any] | None = None,
    changed_input_refs: Sequence[str] | None = None,
    unchanged_input_refs: Sequence[str] | None = None,
    removed_input_refs: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Describe the Graphify rebuild path and return a manifest or typed fallback.

    This function intentionally does not execute Graphify. The external Graphify
    companion remains optional for core survival, so this proof consumes already
    produced `graphify-out` artifacts when present and otherwise emits a typed
    unavailable manifest that release smoke can surface.
    """

    paths = graphify_rebuild_paths(sandbox_root=sandbox_root, input_dir=input_dir)
    rebuild_command = build_graphify_rebuild_command(
        vault_root=vault_root,
        sandbox_root=sandbox_root,
        corpus_manifest_path=corpus_manifest_path,
        input_dir=input_dir,
    )
    failure = _existing_output_failure(paths)
    if failure is None:
        from retrieval.graphify_snapshot_adapter import adapt_graphify_snapshot

        adapter_payload = adapt_graphify_snapshot(
            graph_path=paths["graph_path"],
            summary_path=paths["summary_path"],
            manifest_path=corpus_manifest_path,
            vault_root=vault_root,
            freshness=freshness,
        )
    else:
        reason_code, message = failure
        adapter_payload = build_graphify_snapshot_failure_payload(
            graph_path=paths["graph_path"],
            summary_path=paths["summary_path"],
            manifest_path=corpus_manifest_path,
            vault_root=vault_root,
            reason_code=reason_code,
            message=message,
            freshness=freshness,
        )
    validate_graphify_snapshot_adapter_payload(adapter_payload)
    snapshot_manifest = build_graphify_snapshot_manifest(adapter_payload=adapter_payload)
    status = "available" if snapshot_manifest["status"] == "available" else "unavailable"
    incremental_manifest = None
    has_delta_inputs = any(
        value is not None
        for value in (
            changed_input_refs,
            unchanged_input_refs,
            removed_input_refs,
        )
    )
    if previous_snapshot_manifest is not None or has_delta_inputs:
        if previous_snapshot_manifest is None:
            raise ValueError("Graphify incremental rebuild requires previous_snapshot_manifest")
        incremental_manifest = build_graphify_incremental_manifest(
            previous_snapshot_manifest=previous_snapshot_manifest,
            current_snapshot_manifest=snapshot_manifest,
            changed_input_refs=changed_input_refs,
            unchanged_input_refs=unchanged_input_refs,
            removed_input_refs=removed_input_refs,
            generated_at=generated_at,
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "source_role": SOURCE_ROLE,
        "canonicality": CANONICALITY,
        "mutation_policy": MUTATION_POLICY,
        "execution_policy": EXECUTION_POLICY,
        "input_boundary": _input_boundary(
            vault_root=vault_root,
            sandbox_root=sandbox_root,
            corpus_manifest_path=corpus_manifest_path,
            input_dir=paths["input_dir"],
            rebuild_command=rebuild_command,
        ),
        "output_boundary": _output_boundary(paths),
        "snapshot_manifest": snapshot_manifest,
        "incremental_manifest": incremental_manifest,
        "failure": snapshot_manifest.get("failure"),
        "safety": _safety(),
        "generated_at": generated_at or utc_now_iso(),
    }
    validate_graphify_snapshot_rebuild_result(payload)
    return payload


def validate_graphify_snapshot_rebuild_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Invalid Graphify snapshot rebuild schema_version")
    if payload.get("source_role") != SOURCE_ROLE:
        raise ValueError("Graphify rebuild result must remain a derived rebuild proof")
    if payload.get("canonicality") != CANONICALITY:
        raise ValueError("Graphify rebuild result must not be canonical")
    if payload.get("mutation_policy") != MUTATION_POLICY:
        raise ValueError("Graphify rebuild result must be read-only")
    if payload.get("execution_policy") != EXECUTION_POLICY:
        raise ValueError("Graphify rebuild result must preserve typed unavailable fallback")
    snapshot_manifest = payload.get("snapshot_manifest")
    if not isinstance(snapshot_manifest, Mapping):
        raise ValueError("Graphify rebuild result requires snapshot_manifest")
    validate_graphify_snapshot_manifest(snapshot_manifest)
    if payload.get("status") != snapshot_manifest.get("status"):
        raise ValueError("Graphify rebuild result status must match snapshot manifest status")
    incremental_manifest = payload.get("incremental_manifest")
    if incremental_manifest is not None:
        if not isinstance(incremental_manifest, Mapping):
            raise ValueError("Graphify rebuild incremental_manifest must be an object")
        validate_graphify_incremental_manifest(incremental_manifest)
        if incremental_manifest.get("current_snapshot_manifest_id") != snapshot_manifest.get("manifest_id"):
            raise ValueError("Graphify rebuild incremental manifest must point at current snapshot")
    safety = payload.get("safety")
    if not isinstance(safety, Mapping):
        raise ValueError("Graphify rebuild result requires safety flags")
    required_false_flags = (
        "graphify_is_sot",
        "provider_may_answer_from_graphify_alone",
        "raw_session_copy_allowed",
        "raw_transcript_copy_allowed",
        "vault_write_allowed",
        "provider_raw_session_copied",
        "doc_committed",
    )
    for flag in required_false_flags:
        if safety.get(flag) is not False:
            raise ValueError(f"Graphify rebuild safety flag must be false: {flag}")
    if safety.get("must_verify_against_sot") is not True:
        raise ValueError("Graphify rebuild must require SOT verification")
