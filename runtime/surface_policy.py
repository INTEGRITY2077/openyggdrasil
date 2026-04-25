from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


DOT_RUNTIME_DIRNAME = ".runtime"
TMP_ARTIFACT_DIRNAME = "_tmp"
DEPLOYABLE_RUNTIME_DIRNAME = "runtime"


@dataclass(frozen=True)
class DotRuntimeSurfaceEvaluation:
    schema_version: str
    surface: str
    classification: str
    deployable_runtime_surface: str
    clean_clone_action: str
    creation_policy: str
    tracked_dot_runtime_paths: tuple[str, ...]
    gitignore_mentions_dot_runtime: bool
    release_smoke_status: str
    migration_policy: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "classification": self.classification,
            "deployable_runtime_surface": self.deployable_runtime_surface,
            "clean_clone_action": self.clean_clone_action,
            "creation_policy": self.creation_policy,
            "tracked_dot_runtime_paths": list(self.tracked_dot_runtime_paths),
            "gitignore_mentions_dot_runtime": self.gitignore_mentions_dot_runtime,
            "release_smoke_status": self.release_smoke_status,
            "migration_policy": self.migration_policy,
        }


@dataclass(frozen=True)
class TmpArtifactSurfaceEvaluation:
    schema_version: str
    surface: str
    classification: str
    clean_clone_action: str
    creation_policy: str
    tracked_tmp_paths: tuple[str, ...]
    gitignore_mentions_tmp_root: bool
    gitignore_mentions_nested_tmp: bool
    release_smoke_status: str
    canonical_evidence_policy: str
    cleanup_policy: str
    preserved_evidence_policy: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "classification": self.classification,
            "clean_clone_action": self.clean_clone_action,
            "creation_policy": self.creation_policy,
            "tracked_tmp_paths": list(self.tracked_tmp_paths),
            "gitignore_mentions_tmp_root": self.gitignore_mentions_tmp_root,
            "gitignore_mentions_nested_tmp": self.gitignore_mentions_nested_tmp,
            "release_smoke_status": self.release_smoke_status,
            "canonical_evidence_policy": self.canonical_evidence_policy,
            "cleanup_policy": self.cleanup_policy,
            "preserved_evidence_policy": self.preserved_evidence_policy,
        }


def _normalize_tracked_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_dot_runtime_path(path: str) -> bool:
    normalized = _normalize_tracked_path(path)
    return normalized == DOT_RUNTIME_DIRNAME or normalized.startswith(f"{DOT_RUNTIME_DIRNAME}/")


def _path_has_segment(path: str, segment: str) -> bool:
    return segment in PurePosixPath(_normalize_tracked_path(path)).parts


def _gitignore_mentions_dot_runtime(gitignore_text: str) -> bool:
    for raw_line in gitignore_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line in {".runtime", ".runtime/", "/.runtime", "/.runtime/"}:
            return True
    return False


def _gitignore_mentions_tmp_root(gitignore_text: str) -> bool:
    for raw_line in gitignore_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line in {"_tmp", "_tmp/", "/_tmp", "/_tmp/"}:
            return True
    return False


def _gitignore_mentions_nested_tmp(gitignore_text: str) -> bool:
    for raw_line in gitignore_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line in {"**/_tmp", "**/_tmp/"}:
            return True
    return False


def evaluate_dot_runtime_surface(
    *,
    gitignore_text: str,
    tracked_paths: Iterable[str],
) -> DotRuntimeSurfaceEvaluation:
    """Evaluate whether `.runtime/` remains an ignored local scratch surface."""

    tracked_dot_runtime_paths = tuple(
        sorted(_normalize_tracked_path(path) for path in tracked_paths if _is_dot_runtime_path(path))
    )
    ignored = _gitignore_mentions_dot_runtime(gitignore_text)
    release_smoke_status = "pass" if ignored and not tracked_dot_runtime_paths else "fail"
    return DotRuntimeSurfaceEvaluation(
        schema_version="dot-runtime-surface-policy.v1",
        surface=DOT_RUNTIME_DIRNAME,
        classification="ignored_local_scratch_artifact_root",
        deployable_runtime_surface=DEPLOYABLE_RUNTIME_DIRNAME,
        clean_clone_action="do_not_create_eagerly",
        creation_policy="create_only_on_demand_for_test_probe_or_generated_artifacts",
        tracked_dot_runtime_paths=tracked_dot_runtime_paths,
        gitignore_mentions_dot_runtime=ignored,
        release_smoke_status=release_smoke_status,
        migration_policy="defer_deletion_or_migration_to_dedicated_checklist",
    )


def evaluate_tmp_artifact_surface(
    *,
    gitignore_text: str,
    tracked_paths: Iterable[str],
) -> TmpArtifactSurfaceEvaluation:
    """Evaluate whether `_tmp/` remains ignored generated scratch, never SOT."""

    tracked_tmp_paths = tuple(
        sorted(
            _normalize_tracked_path(path)
            for path in tracked_paths
            if _path_has_segment(path, TMP_ARTIFACT_DIRNAME)
        )
    )
    ignores_root = _gitignore_mentions_tmp_root(gitignore_text)
    ignores_nested = _gitignore_mentions_nested_tmp(gitignore_text)
    release_smoke_status = "pass" if ignores_root and ignores_nested and not tracked_tmp_paths else "fail"
    return TmpArtifactSurfaceEvaluation(
        schema_version="tmp-artifact-surface-policy.v1",
        surface=TMP_ARTIFACT_DIRNAME,
        classification="ignored_generated_scratch_artifact_root",
        clean_clone_action="do_not_create_eagerly",
        creation_policy="create_only_on_demand_for_probe_or_generated_artifact",
        tracked_tmp_paths=tracked_tmp_paths,
        gitignore_mentions_tmp_root=ignores_root,
        gitignore_mentions_nested_tmp=ignores_nested,
        release_smoke_status=release_smoke_status,
        canonical_evidence_policy="never_treat_tmp_artifact_as_sot",
        cleanup_policy="safe_to_delete_when_not_needed_for_active_local_debugging",
        preserved_evidence_policy="promote_needed_summary_to_tracked_history_before_cleanup",
    )
