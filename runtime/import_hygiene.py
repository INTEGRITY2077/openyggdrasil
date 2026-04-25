from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


IMPORT_HYGIENE_SCHEMA_VERSION = "import-hygiene-policy.v1"
MIGRATION_STRATEGY = "bounded_no_broad_package_churn"


RUNTIME_ENTRYPOINT_PATHS = {
    "runtime/attachments/repair_attachment.py",
    "runtime/attachments/validate_attachment.py",
    "runtime/runner/hermes_live_replay_regression.py",
    "runtime/runner/real_ux_regression.py",
    "runtime/runner/real_ux_regression_summary.py",
}


MIGRATION_PLAN = (
    "keep runtime import smoke green before each import migration",
    "retain top-level compatibility shims until provider imports migrate",
    "move runtime entrypoints toward package/module invocation in bounded follow-up commits",
    "keep test bootstraps local until pytest path configuration is introduced once",
    "classify provider harness and provider skill references before touching vendored/provider surfaces",
)


@dataclass(frozen=True)
class ImportPathInsertDecision:
    path: str
    classification: str
    retention_status: str


@dataclass(frozen=True)
class ImportHygieneSummary:
    schema_version: str
    total_count: int
    runtime_entrypoint_count: int
    test_bootstrap_count: int
    provider_tooling_count: int
    unknown_paths: tuple[str, ...]
    migration_strategy: str
    migration_plan: tuple[str, ...]
    runtime_import_smoke_required: bool

    @property
    def ok(self) -> bool:
        return not self.unknown_paths

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "total_count": self.total_count,
            "runtime_entrypoint_count": self.runtime_entrypoint_count,
            "test_bootstrap_count": self.test_bootstrap_count,
            "provider_tooling_count": self.provider_tooling_count,
            "unknown_paths": list(self.unknown_paths),
            "migration_strategy": self.migration_strategy,
            "migration_plan": list(self.migration_plan),
            "runtime_import_smoke_required": self.runtime_import_smoke_required,
            "ok": self.ok,
        }


def _normalize_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def classify_path_insert_site(path: str) -> ImportPathInsertDecision:
    normalized = _normalize_path(path)
    if normalized in RUNTIME_ENTRYPOINT_PATHS:
        return ImportPathInsertDecision(
            path=normalized,
            classification="runtime_entrypoint_bootstrap",
            retention_status="migrate_to_package_invocation_without_broad_churn",
        )
    if normalized.startswith("tests/"):
        return ImportPathInsertDecision(
            path=normalized,
            classification="test_bootstrap",
            retention_status="retain_until_single_pytest_path_config",
        )
    if normalized.startswith("providers/") or normalized.startswith("projects/"):
        return ImportPathInsertDecision(
            path=normalized,
            classification="provider_or_project_tooling",
            retention_status="classify_before_runtime_import_migration",
        )
    return ImportPathInsertDecision(
        path=normalized,
        classification="unknown",
        retention_status="requires_review_before_commit",
    )


def import_hygiene_summary(paths: Iterable[str]) -> ImportHygieneSummary:
    decisions = [classify_path_insert_site(path) for path in paths]
    runtime_entrypoint_count = sum(
        1 for decision in decisions if decision.classification == "runtime_entrypoint_bootstrap"
    )
    test_bootstrap_count = sum(1 for decision in decisions if decision.classification == "test_bootstrap")
    provider_tooling_count = sum(
        1 for decision in decisions if decision.classification == "provider_or_project_tooling"
    )
    unknown_paths = tuple(
        sorted(decision.path for decision in decisions if decision.classification == "unknown")
    )
    return ImportHygieneSummary(
        schema_version=IMPORT_HYGIENE_SCHEMA_VERSION,
        total_count=len(decisions),
        runtime_entrypoint_count=runtime_entrypoint_count,
        test_bootstrap_count=test_bootstrap_count,
        provider_tooling_count=provider_tooling_count,
        unknown_paths=unknown_paths,
        migration_strategy=MIGRATION_STRATEGY,
        migration_plan=MIGRATION_PLAN,
        runtime_import_smoke_required=True,
    )
