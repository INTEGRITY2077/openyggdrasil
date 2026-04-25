from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


PROVIDER_TOOLING_CLASSIFICATION_VERSION = "provider-tooling-classification.v1"
NON_RUNTIME_STATUS = "optional_provider_tooling_not_openyggdrasil_runtime"


@dataclass(frozen=True)
class ProviderToolingDecision:
    path: str
    classification: str
    runtime_status: str
    release_smoke_policy: str
    next_action: str | None = None


@dataclass(frozen=True)
class ProviderToolingSummary:
    schema_version: str
    total_count: int
    vendored_skill_pack_count: int
    provider_harness_count: int
    graphify_poc_count: int
    provider_project_count: int
    provider_profile_surface_count: int
    provider_packaging_doc_count: int
    project_doc_count: int
    unknown_paths: tuple[str, ...]
    runtime_status: str

    @property
    def ok(self) -> bool:
        return not self.unknown_paths

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "total_count": self.total_count,
            "vendored_skill_pack_count": self.vendored_skill_pack_count,
            "provider_harness_count": self.provider_harness_count,
            "graphify_poc_count": self.graphify_poc_count,
            "provider_project_count": self.provider_project_count,
            "provider_profile_surface_count": self.provider_profile_surface_count,
            "provider_packaging_doc_count": self.provider_packaging_doc_count,
            "project_doc_count": self.project_doc_count,
            "unknown_paths": list(self.unknown_paths),
            "runtime_status": self.runtime_status,
            "ok": self.ok,
        }


def _normalize_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def classify_provider_tooling_path(path: str) -> ProviderToolingDecision:
    normalized = _normalize_path(path)
    if normalized.startswith("providers/hermes/skills/"):
        return ProviderToolingDecision(
            path=normalized,
            classification="vendored_provider_skill_pack",
            runtime_status=NON_RUNTIME_STATUS,
            release_smoke_policy="do_not_execute_as_openyggdrasil_runtime",
            next_action=None,
        )
    if normalized.startswith("providers/hermes/projects/harness/"):
        return ProviderToolingDecision(
            path=normalized,
            classification="provider_harness_reference_tooling",
            runtime_status=NON_RUNTIME_STATUS,
            release_smoke_policy="do_not_treat_provider_harness_as_deploy_runtime",
            next_action=None,
        )
    if normalized.startswith("providers/hermes/projects/graphify-poc/") or normalized.startswith(
        "projects/graphify-poc/"
    ):
        return ProviderToolingDecision(
            path=normalized,
            classification="graphify_poc_project_tooling",
            runtime_status=NON_RUNTIME_STATUS,
            release_smoke_policy="exclude_from_core_runtime_release_smoke_until_phase_8",
            next_action="Phase 8 derived graph safety/release smoke",
        )
    if normalized.startswith("providers/hermes/projects/"):
        return ProviderToolingDecision(
            path=normalized,
            classification="provider_project_tooling",
            runtime_status=NON_RUNTIME_STATUS,
            release_smoke_policy="do_not_treat_provider_project_as_deploy_runtime",
            next_action=None,
        )
    if normalized.startswith(
        (
            "providers/hermes/hooks/",
            "providers/hermes/memories/",
            "providers/hermes/policy/",
            "providers/hermes/vault/",
        )
    ):
        return ProviderToolingDecision(
            path=normalized,
            classification="provider_profile_surface",
            runtime_status=NON_RUNTIME_STATUS,
            release_smoke_policy="not_canonical_runtime_state",
            next_action=None,
        )
    if normalized.startswith("providers/"):
        return ProviderToolingDecision(
            path=normalized,
            classification="provider_packaging_documentation",
            runtime_status=NON_RUNTIME_STATUS,
            release_smoke_policy="documentation_or_provider_manifest_only",
            next_action=None,
        )
    if normalized == "projects/README.md":
        return ProviderToolingDecision(
            path=normalized,
            classification="project_documentation",
            runtime_status=NON_RUNTIME_STATUS,
            release_smoke_policy="documentation_only",
            next_action=None,
        )
    return ProviderToolingDecision(
        path=normalized,
        classification="unknown",
        runtime_status="requires_review_before_commit",
        release_smoke_policy="requires_review_before_release_smoke",
        next_action="P7.CR1.phase-close-code-review",
    )


def provider_tooling_summary(paths: Iterable[str]) -> ProviderToolingSummary:
    decisions = [classify_provider_tooling_path(path) for path in paths]
    vendored_skill_pack_count = sum(
        1 for decision in decisions if decision.classification == "vendored_provider_skill_pack"
    )
    provider_harness_count = sum(
        1 for decision in decisions if decision.classification == "provider_harness_reference_tooling"
    )
    graphify_poc_count = sum(1 for decision in decisions if decision.classification == "graphify_poc_project_tooling")
    provider_project_count = sum(1 for decision in decisions if decision.classification == "provider_project_tooling")
    provider_profile_surface_count = sum(
        1 for decision in decisions if decision.classification == "provider_profile_surface"
    )
    provider_packaging_doc_count = sum(
        1 for decision in decisions if decision.classification == "provider_packaging_documentation"
    )
    project_doc_count = sum(1 for decision in decisions if decision.classification == "project_documentation")
    unknown_paths = tuple(
        sorted(decision.path for decision in decisions if decision.classification == "unknown")
    )
    return ProviderToolingSummary(
        schema_version=PROVIDER_TOOLING_CLASSIFICATION_VERSION,
        total_count=len(decisions),
        vendored_skill_pack_count=vendored_skill_pack_count,
        provider_harness_count=provider_harness_count,
        graphify_poc_count=graphify_poc_count,
        provider_project_count=provider_project_count,
        provider_profile_surface_count=provider_profile_surface_count,
        provider_packaging_doc_count=provider_packaging_doc_count,
        project_doc_count=project_doc_count,
        unknown_paths=unknown_paths,
        runtime_status=NON_RUNTIME_STATUS,
    )
