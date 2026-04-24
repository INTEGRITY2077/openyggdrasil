from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable


def _frozen(values: Iterable[str]) -> FrozenSet[str]:
    return frozenset(str(value) for value in values)


@dataclass(frozen=True)
class RoleSpec:
    role: str
    capabilities: FrozenSet[str]
    write_scopes: FrozenSet[str]
    inference_modes: FrozenSet[str]
    allowed_commands: FrozenSet[str] = frozenset()
    allowed_job_types: FrozenSet[str] = frozenset()
    allowed_packet_types: FrozenSet[str] = frozenset()


ROLE_REGISTRY: dict[str, RoleSpec] = {
    "observer": RoleSpec(
        role="observer",
        capabilities=_frozen(["ingest", "query", "lint", "system"]),
        write_scopes=_frozen(["result"]),
        inference_modes=_frozen(["deterministic"]),
        allowed_commands=_frozen(["execute_lint"]),
    ),
    "postman": RoleSpec(
        role="postman",
        capabilities=_frozen(["ingest", "query", "lint", "system"]),
        write_scopes=_frozen(["mailbox"]),
        inference_modes=_frozen(["deterministic", "hermes_runtime"]),
        allowed_commands=_frozen(["execute_lint", "execute_deep_search", "execute_decision_capture"]),
        allowed_packet_types=_frozen(["graph_hint", "lint_alert", "decision_candidate"]),
    ),
    "sot_writer": RoleSpec(
        role="sot_writer",
        capabilities=_frozen(["ingest"]),
        write_scopes=_frozen(["vault"]),
        inference_modes=_frozen(["deterministic"]),
        allowed_job_types=_frozen(["promotion"]),
    ),
    "graph_builder": RoleSpec(
        role="graph_builder",
        capabilities=_frozen(["query"]),
        write_scopes=_frozen(["graph"]),
        inference_modes=_frozen(["hermes_runtime"]),
        allowed_job_types=_frozen(["graph_rebuild"]),
    ),
    "deep_search_executor": RoleSpec(
        role="deep_search_executor",
        capabilities=_frozen(["query"]),
        write_scopes=_frozen(["result"]),
        inference_modes=_frozen(["deterministic"]),
        allowed_commands=_frozen(["execute_deep_search"]),
    ),
    "lint_executor": RoleSpec(
        role="lint_executor",
        capabilities=_frozen(["lint"]),
        write_scopes=_frozen(["result"]),
        inference_modes=_frozen(["deterministic"]),
        allowed_commands=_frozen(["execute_lint"]),
    ),
    "decision_capture_executor": RoleSpec(
        role="decision_capture_executor",
        capabilities=_frozen(["ingest"]),
        write_scopes=_frozen(["result"]),
        inference_modes=_frozen(["subagent_headless"]),
        allowed_commands=_frozen(["execute_decision_capture"]),
    ),
    "command-worker": RoleSpec(
        role="command-worker",
        capabilities=_frozen(["ingest", "query", "system"]),
        write_scopes=_frozen(["queue"]),
        inference_modes=_frozen(["deterministic", "hermes_runtime"]),
        allowed_job_types=_frozen(["promotion", "graph_rebuild"]),
    ),
    "hermes": RoleSpec(
        role="hermes",
        capabilities=_frozen(["query", "system"]),
        write_scopes=_frozen(["none"]),
        inference_modes=_frozen(["deterministic", "hermes_runtime"]),
        allowed_packet_types=_frozen(["graph_hint", "lint_alert"]),
    ),
}


def get_role_spec(role: str) -> RoleSpec:
    try:
        return ROLE_REGISTRY[role]
    except KeyError as exc:
        raise RuntimeError(f"Unknown role: {role}") from exc


def _ensure_capability(spec: RoleSpec, capability: str) -> None:
    if capability not in spec.capabilities:
        raise RuntimeError(
            f"Role '{spec.role}' is not allowed to use capability '{capability}'"
        )


def _ensure_write_scope(spec: RoleSpec, write_scope: str) -> None:
    if write_scope not in spec.write_scopes:
        raise RuntimeError(
            f"Role '{spec.role}' is not allowed to write scope '{write_scope}'"
        )


def _ensure_inference_mode(spec: RoleSpec, inference_mode: str) -> None:
    if inference_mode not in spec.inference_modes:
        raise RuntimeError(
            f"Role '{spec.role}' is not allowed to use inference mode '{inference_mode}'"
        )


def ensure_role_can_route_command(*, role: str, message_type: str, capability: str) -> None:
    spec = get_role_spec(role)
    if message_type not in spec.allowed_commands:
        raise RuntimeError(
            f"Role '{role}' is not allowed to route command '{message_type}'"
        )
    _ensure_capability(spec, capability)


def ensure_role_can_handle_command(
    *,
    role: str,
    message_type: str,
    capability: str,
    inference_mode: str,
    write_scope: str,
) -> None:
    spec = get_role_spec(role)
    if message_type not in spec.allowed_commands:
        raise RuntimeError(
            f"Role '{role}' is not allowed to handle command '{message_type}'"
        )
    _ensure_capability(spec, capability)
    _ensure_inference_mode(spec, inference_mode)
    _ensure_write_scope(spec, write_scope)


def ensure_role_can_run_job(
    *,
    role: str,
    job_type: str,
    capability: str,
    inference_mode: str,
    write_scope: str,
) -> None:
    spec = get_role_spec(role)
    if job_type not in spec.allowed_job_types:
        raise RuntimeError(
            f"Role '{role}' is not allowed to run job '{job_type}'"
        )
    _ensure_capability(spec, capability)
    _ensure_inference_mode(spec, inference_mode)
    _ensure_write_scope(spec, write_scope)


def ensure_role_can_emit_packet(*, role: str, packet_type: str) -> None:
    spec = get_role_spec(role)
    if packet_type not in spec.allowed_packet_types:
        raise RuntimeError(
            f"Role '{role}' is not allowed to emit packet '{packet_type}'"
        )


def ensure_scope_satisfies_write_scope(*, write_scope: str, scope: dict[str, object]) -> None:
    if write_scope == "vault" and not scope.get("vault_path"):
        raise RuntimeError("write_scope 'vault' requires scope.vault_path")
    if write_scope == "graph" and not scope.get("graph_path"):
        raise RuntimeError("write_scope 'graph' requires scope.graph_path")
