from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SANDBOX_RUNTIME_CANDIDATE = "sandbox-runtime"
DOCKER_FALLBACK_POLICY = "fallback_or_stronger_isolation_only"
LEASE_SECURITY_UNAVAILABLE = "lease_security_unavailable"

OFFICIAL_SANDBOX_SOT_REFS = (
    "https://code.claude.com/docs/en/sandboxing",
    "https://code.claude.com/docs/en/configuration#sandbox-settings",
    "https://github.com/anthropic-experimental/sandbox-runtime",
    "https://www.npmjs.com/package/@anthropic-ai/sandbox-runtime",
    "https://github.com/containers/bubblewrap",
)


@dataclass(frozen=True)
class ProcessSandboxRuntimeDecision:
    schema_version: str
    first_candidate: str
    docker_policy: str
    platform: str
    platform_support_status: str
    sandbox_required: bool
    sandbox_runtime_available: bool
    dependencies_available: bool
    native_windows_support_assumed: bool
    sandbox_backend: str | None
    filesystem_policy: str
    network_policy: str
    allowed_domains: tuple[str, ...]
    allow_all_unix_sockets: bool
    enable_weaker_network_isolation: bool
    unix_socket_policy: str
    weaker_network_isolation_policy: str
    silent_unsandboxed_fallback_allowed: bool
    execution_decision: str
    typed_unavailable_status: str | None
    reason_code: str
    official_sot_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "first_candidate": self.first_candidate,
            "docker_policy": self.docker_policy,
            "platform": self.platform,
            "platform_support_status": self.platform_support_status,
            "sandbox_required": self.sandbox_required,
            "sandbox_runtime_available": self.sandbox_runtime_available,
            "dependencies_available": self.dependencies_available,
            "native_windows_support_assumed": self.native_windows_support_assumed,
            "sandbox_backend": self.sandbox_backend,
            "filesystem_policy": self.filesystem_policy,
            "network_policy": self.network_policy,
            "allowed_domains": list(self.allowed_domains),
            "allow_all_unix_sockets": self.allow_all_unix_sockets,
            "enable_weaker_network_isolation": self.enable_weaker_network_isolation,
            "unix_socket_policy": self.unix_socket_policy,
            "weaker_network_isolation_policy": self.weaker_network_isolation_policy,
            "silent_unsandboxed_fallback_allowed": self.silent_unsandboxed_fallback_allowed,
            "execution_decision": self.execution_decision,
            "typed_unavailable_status": self.typed_unavailable_status,
            "reason_code": self.reason_code,
            "official_sot_refs": list(self.official_sot_refs),
        }


def _normalize_platform(platform: str) -> str:
    value = platform.strip().lower()
    if value.startswith(("win", "cygwin", "msys")):
        return "windows"
    if value in {"darwin", "mac", "macos", "osx"}:
        return "macos"
    if value in {"wsl", "wsl2"}:
        return "wsl2"
    if value.startswith("linux"):
        return "linux"
    return value or "unknown"


def _network_policy(allowed_domains: tuple[str, ...]) -> str:
    if allowed_domains:
        return "explicit_domain_allowlist"
    return "no_network_by_default"


def build_process_sandbox_runtime_decision(
    *,
    platform: str,
    sandbox_required: bool,
    sandbox_runtime_available: bool,
    bubblewrap_available: bool = False,
    socat_available: bool = False,
    allowed_domains: Iterable[str] = (),
    allow_all_unix_sockets: bool = False,
    enable_weaker_network_isolation: bool = False,
) -> ProcessSandboxRuntimeDecision:
    """Build the Phase 7 process sandbox decision for helper/subprocess execution."""

    normalized_platform = _normalize_platform(platform)
    normalized_allowed_domains = tuple(sorted({domain.strip().lower() for domain in allowed_domains if domain.strip()}))
    if normalized_platform == "macos":
        platform_support_status = "supported"
        dependencies_available = sandbox_runtime_available
        sandbox_backend = "seatbelt"
    elif normalized_platform in {"linux", "wsl2"}:
        platform_support_status = "supported"
        dependencies_available = sandbox_runtime_available and bubblewrap_available and socat_available
        sandbox_backend = "bubblewrap"
    elif normalized_platform == "windows":
        platform_support_status = "unsupported_native_windows"
        dependencies_available = False
        sandbox_backend = None
    else:
        platform_support_status = "unknown_platform"
        dependencies_available = False
        sandbox_backend = None

    escape_route_requested = allow_all_unix_sockets or enable_weaker_network_isolation
    sandbox_ready = platform_support_status == "supported" and sandbox_runtime_available and dependencies_available
    if escape_route_requested:
        execution_decision = "fail_closed"
        typed_unavailable_status = LEASE_SECURITY_UNAVAILABLE
        reason_code = "sandbox_escape_route_requested"
    elif sandbox_required and not sandbox_ready:
        execution_decision = "fail_closed"
        typed_unavailable_status = LEASE_SECURITY_UNAVAILABLE
        reason_code = "sandbox_unavailable"
    elif sandbox_ready:
        execution_decision = "allow_sandboxed"
        typed_unavailable_status = None
        reason_code = "sandbox_runtime_available"
    else:
        execution_decision = "optional_sandbox_unavailable"
        typed_unavailable_status = "sandbox_unavailable"
        reason_code = "sandbox_unavailable_optional"

    return ProcessSandboxRuntimeDecision(
        schema_version="process_sandbox_runtime_decision.v1",
        first_candidate=SANDBOX_RUNTIME_CANDIDATE,
        docker_policy=DOCKER_FALLBACK_POLICY,
        platform=normalized_platform,
        platform_support_status=platform_support_status,
        sandbox_required=sandbox_required,
        sandbox_runtime_available=sandbox_runtime_available,
        dependencies_available=dependencies_available,
        native_windows_support_assumed=False,
        sandbox_backend=sandbox_backend,
        filesystem_policy="allow_write_workspace_only_with_explicit_extra_paths",
        network_policy=_network_policy(normalized_allowed_domains),
        allowed_domains=normalized_allowed_domains,
        allow_all_unix_sockets=allow_all_unix_sockets,
        enable_weaker_network_isolation=enable_weaker_network_isolation,
        unix_socket_policy="deny_broad_unix_socket_escape_by_default",
        weaker_network_isolation_policy="deny_weakened_nested_or_network_isolation_by_default",
        silent_unsandboxed_fallback_allowed=False,
        execution_decision=execution_decision,
        typed_unavailable_status=typed_unavailable_status,
        reason_code=reason_code,
        official_sot_refs=OFFICIAL_SANDBOX_SOT_REFS,
    )
