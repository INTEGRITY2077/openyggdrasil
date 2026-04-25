from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


DOT_RUNTIME_DIRNAME = ".runtime"
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


def _normalize_tracked_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_dot_runtime_path(path: str) -> bool:
    normalized = _normalize_tracked_path(path)
    return normalized == DOT_RUNTIME_DIRNAME or normalized.startswith(f"{DOT_RUNTIME_DIRNAME}/")


def _gitignore_mentions_dot_runtime(gitignore_text: str) -> bool:
    for raw_line in gitignore_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line in {".runtime", ".runtime/", "/.runtime", "/.runtime/"}:
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
