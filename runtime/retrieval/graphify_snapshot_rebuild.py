from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

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
SOURCE_ROLE = "derived_graph_snapshot_rebuild"
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
        "common/graphify-poc/run_graphify_pipeline.py",
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
