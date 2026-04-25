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


@dataclass(frozen=True)
class IgnoredVerificationSurfaceDecision:
    path: str
    classification: str
    cleanup_action: str
    evidence_policy: str


@dataclass(frozen=True)
class IgnoredVerificationCleanupPlan:
    schema_version: str
    total_count: int
    safe_cleanup_paths: tuple[str, ...]
    preserved_paths: tuple[str, ...]
    unknown_paths: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.unknown_paths

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "total_count": self.total_count,
            "safe_cleanup_paths": list(self.safe_cleanup_paths),
            "preserved_paths": list(self.preserved_paths),
            "unknown_paths": list(self.unknown_paths),
            "ok": self.ok,
        }


def _normalize_tracked_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.endswith("/") and normalized != "/":
        normalized = normalized.rstrip("/")
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


def classify_ignored_verification_surface(path: str) -> IgnoredVerificationSurfaceDecision:
    normalized = _normalize_tracked_path(path)
    parts = PurePosixPath(normalized).parts
    if (
        _is_dot_runtime_path(normalized)
        or _path_has_segment(normalized, TMP_ARTIFACT_DIRNAME)
        or ".pytest_cache" in parts
        or "__pycache__" in parts
    ):
        return IgnoredVerificationSurfaceDecision(
            path=normalized,
            classification="generated_verification_artifact",
            cleanup_action="safe_to_delete_after_history_inventory",
            evidence_policy="tracked_history_must_record_inventory_before_cleanup",
        )
    if (
        normalized == "doc"
        or normalized.startswith("doc/")
        or normalized == ".yggdrasil"
        or normalized.startswith(".yggdrasil/")
        or "memories" in parts
        or "ops" in parts
        or "_archive" in parts
        or normalized == "agent-list.ko.md"
        or normalized.endswith("/graphify-corpus.manifest.json")
        or normalized.startswith("vault/.obsidian")
    ):
        return IgnoredVerificationSurfaceDecision(
            path=normalized,
            classification="preserve_local_or_user_sensitive_surface",
            cleanup_action="preserve_without_explicit_review",
            evidence_policy="do_not_delete_as_verification_cleanup",
        )
    if normalized == "tests" or normalized.startswith("tests/") or "tests" in parts:
        return IgnoredVerificationSurfaceDecision(
            path=normalized,
            classification="local_verification_source",
            cleanup_action="preserve_until_tracked_or_reviewed",
            evidence_policy="do_not_delete_without_dedicated_test_surface_review",
        )
    return IgnoredVerificationSurfaceDecision(
        path=normalized,
        classification="unknown",
        cleanup_action="requires_review_before_cleanup",
        evidence_policy="do_not_delete_without_classification",
    )


def ignored_verification_cleanup_plan(paths: Iterable[str]) -> IgnoredVerificationCleanupPlan:
    decisions = [classify_ignored_verification_surface(path) for path in paths]
    safe_cleanup_paths = tuple(
        sorted(
            decision.path
            for decision in decisions
            if decision.cleanup_action == "safe_to_delete_after_history_inventory"
        )
    )
    preserved_paths = tuple(
        sorted(
            decision.path
            for decision in decisions
            if decision.cleanup_action
            in {
                "preserve_without_explicit_review",
                "preserve_until_tracked_or_reviewed",
            }
        )
    )
    unknown_paths = tuple(
        sorted(decision.path for decision in decisions if decision.cleanup_action == "requires_review_before_cleanup")
    )
    return IgnoredVerificationCleanupPlan(
        schema_version="ignored-verification-cleanup-policy.v1",
        total_count=len(decisions),
        safe_cleanup_paths=safe_cleanup_paths,
        preserved_paths=preserved_paths,
        unknown_paths=unknown_paths,
    )
