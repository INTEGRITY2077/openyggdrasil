from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema

from attachments.bootstrap_contract import prove_provider_bootstrap_contract
from attachments.deploy_skill import build_deploy_plan
from attachments.provider_attachment import (
    build_session_uid,
    bootstrap_skill_provider_session,
    session_uid_path_component,
)
from attachments.validate_attachment import validate_workspace
from harness_common import utc_now_iso


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
SCHEMA_FILENAME = "provider_cold_start_healthcheck.v1.schema.json"
DEFAULT_BACKEND_PREFERENCE = ("sandbox-runtime", "bubblewrap", "socat")
CORE_SOURCE_PATHS = (
    Path("SKILL.md"),
    Path("runtime/attachments/validate_attachment.py"),
    Path("runtime/attachments/repair_attachment.py"),
    Path("runtime/attachments/deploy_skill.py"),
    Path("runtime/attachments/deploy_hermes_profile_skill.py"),
    Path("runtime/attachments/provider_cold_start_healthcheck.py"),
    Path("contracts/provider_cold_start_healthcheck.v1.schema.json"),
)
MODULE_EFFORT_PATHS = (
    Path("contracts/module_effort_requirement.v1.schema.json"),
    Path("contracts/module_effort_plan.v1.schema.json"),
    Path("runtime/reasoning/module_effort_requirements.py"),
)

CommandRunner = Callable[[list[str], int], tuple[int, str, str]]
Which = Callable[[str], str | None]


@lru_cache(maxsize=1)
def load_provider_cold_start_healthcheck_schema() -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / SCHEMA_FILENAME).read_text(encoding="utf-8"))


def validate_provider_cold_start_healthcheck(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_provider_cold_start_healthcheck_schema(),
    )


def marker_path_for(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
) -> Path:
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return (
        workspace_root.resolve()
        / ".yggdrasil"
        / "healthcheck"
        / "provider_cold_start"
        / f"{session_uid_path_component(session_uid)}.json"
    )


def _evidence(kind: str, path_hint: str, detail: str | None = None) -> dict[str, str | None]:
    return {"kind": kind, "path_hint": path_hint, "detail": detail}


def _help(reason_code: str, action: str, why_user_needed: str) -> dict[str, str]:
    return {
        "reason_code": reason_code,
        "action": action,
        "why_user_needed": why_user_needed,
    }


def _attempt(
    *,
    route_id: str,
    attempt_index: int,
    max_attempts: int,
    status: str,
    reason_code: str,
    comment: str,
    evidence_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "route_id": route_id,
        "attempt_index": attempt_index,
        "max_attempts": max_attempts,
        "status": status,
        "reason_code": reason_code,
        "comment": comment,
        "evidence_refs": evidence_refs or [],
    }


def _check(
    *,
    check_id: str,
    label: str,
    blocking: bool,
    attempts: list[dict[str, Any]],
    user_help: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    status = "pass" if all(row["status"] == "pass" for row in attempts) else "fail"
    if all(row["status"] == "skipped" for row in attempts):
        status = "skipped"
    reason_codes = sorted({str(row["reason_code"]) for row in attempts})
    evidence_refs: list[dict[str, Any]] = []
    for row in attempts:
        evidence_refs.extend(row["evidence_refs"])
    failing = [row for row in attempts if row["status"] == "fail"]
    comment = failing[-1]["comment"] if failing else attempts[-1]["comment"]
    help_items = user_help or []
    return {
        "check_id": check_id,
        "label": label,
        "status": status,
        "blocking": blocking,
        "attempts": attempts,
        "reason_codes": reason_codes,
        "comment": comment,
        "user_help_required": bool(help_items) and status == "fail",
        "user_help": help_items if status == "fail" else [],
        "evidence_refs": evidence_refs,
    }


def _run_command(command: list[str], timeout_seconds: int) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _workspace_exists_check(workspace_root: Path) -> dict[str, Any]:
    exists = workspace_root.exists() and workspace_root.is_dir()
    return _check(
        check_id="workspace.root.exists",
        label="Workspace root exists",
        blocking=True,
        attempts=[
            _attempt(
                route_id="local_path",
                attempt_index=1,
                max_attempts=1,
                status="pass" if exists else "fail",
                reason_code="workspace_root_exists" if exists else "workspace_root_missing",
                comment=(
                    f"Workspace root is available: {workspace_root}"
                    if exists
                    else f"Workspace root is missing or not a directory: {workspace_root}"
                ),
                evidence_refs=[_evidence("local_file", str(workspace_root))],
            )
        ],
        user_help=[
            _help(
                "workspace_root_missing",
                "Open or clone the OpenYggdrasil repository and run the provider skill from that workspace root.",
                "The provider cannot safely infer the canonical repository root.",
            )
        ],
    )


def _workspace_writable_check(workspace_root: Path) -> dict[str, Any]:
    health_dir = workspace_root / ".yggdrasil" / "healthcheck"
    probe_path = health_dir / "write-probe.tmp"
    attempts: list[dict[str, Any]] = []
    try:
        health_dir.mkdir(parents=True, exist_ok=True)
        attempts.append(
            _attempt(
                route_id="create_healthcheck_dir",
                attempt_index=1,
                max_attempts=3,
                status="pass",
                reason_code="healthcheck_dir_writable",
                comment=f"Created or reused healthcheck directory: {health_dir}",
                evidence_refs=[_evidence("local_file", str(health_dir))],
            )
        )
    except Exception as exc:  # noqa: BLE001
        attempts.append(
            _attempt(
                route_id="create_healthcheck_dir",
                attempt_index=1,
                max_attempts=3,
                status="fail",
                reason_code="healthcheck_dir_not_writable",
                comment=f"Cannot create healthcheck directory: {exc}",
                evidence_refs=[_evidence("runtime_probe", str(health_dir), exc.__class__.__name__)],
            )
        )
        return _check(
            check_id="workspace.runtime_state.writable",
            label="Workspace runtime state is writable",
            blocking=True,
            attempts=attempts,
            user_help=[
                _help(
                    "healthcheck_dir_not_writable",
                    "Grant write access to the repository-local .yggdrasil directory or choose a writable workspace clone.",
                    "OpenYggdrasil must write session-bound runtime state before it can attach a provider.",
                )
            ],
        )

    try:
        probe_path.write_text("ok\n", encoding="utf-8")
        attempts.append(
            _attempt(
                route_id="write_probe_file",
                attempt_index=2,
                max_attempts=3,
                status="pass",
                reason_code="runtime_state_file_writable",
                comment=f"Wrote runtime probe file: {probe_path}",
                evidence_refs=[_evidence("local_file", str(probe_path))],
            )
        )
    except Exception as exc:  # noqa: BLE001
        attempts.append(
            _attempt(
                route_id="write_probe_file",
                attempt_index=2,
                max_attempts=3,
                status="fail",
                reason_code="runtime_state_file_not_writable",
                comment=f"Cannot write runtime probe file: {exc}",
                evidence_refs=[_evidence("runtime_probe", str(probe_path), exc.__class__.__name__)],
            )
        )
        return _check(
            check_id="workspace.runtime_state.writable",
            label="Workspace runtime state is writable",
            blocking=True,
            attempts=attempts,
            user_help=[
                _help(
                    "runtime_state_file_not_writable",
                    "Grant file write permission under .yggdrasil or move the repo to a writable path.",
                    "The provider cannot persist attachment descriptors, inbox bindings, or healthcheck markers.",
                )
            ],
        )

    try:
        probe_path.unlink(missing_ok=True)
        attempts.append(
            _attempt(
                route_id="cleanup_probe_file",
                attempt_index=3,
                max_attempts=3,
                status="pass",
                reason_code="runtime_state_cleanup_ok",
                comment=f"Cleaned runtime probe file: {probe_path}",
                evidence_refs=[_evidence("runtime_probe", str(probe_path))],
            )
        )
    except Exception as exc:  # noqa: BLE001
        attempts.append(
            _attempt(
                route_id="cleanup_probe_file",
                attempt_index=3,
                max_attempts=3,
                status="fail",
                reason_code="runtime_state_cleanup_failed",
                comment=f"Runtime probe file was writable but cleanup failed: {exc}",
                evidence_refs=[_evidence("runtime_probe", str(probe_path), exc.__class__.__name__)],
            )
        )

    return _check(
        check_id="workspace.runtime_state.writable",
        label="Workspace runtime state is writable",
        blocking=True,
        attempts=attempts,
        user_help=[
            _help(
                "runtime_state_cleanup_failed",
                "Inspect filesystem locking or antivirus interference under .yggdrasil.",
                "The provider can write state, but repeated cold-start checks may leave stale probe files.",
            )
        ],
    )


def _source_files_check(workspace_root: Path) -> dict[str, Any]:
    missing = [path for path in CORE_SOURCE_PATHS if not (workspace_root / path).exists()]
    return _check(
        check_id="skill.install_sources.present",
        label="Provider skill install sources are present",
        blocking=True,
        attempts=[
            _attempt(
                route_id="repo_source_inventory",
                attempt_index=1,
                max_attempts=1,
                status="pass" if not missing else "fail",
                reason_code="skill_sources_present" if not missing else "skill_sources_missing",
                comment=(
                    "All provider skill source files are present."
                    if not missing
                    else "Missing provider skill source files: "
                    + ", ".join(path.as_posix() for path in missing)
                ),
                evidence_refs=[_evidence("local_file", (workspace_root / path).as_posix()) for path in CORE_SOURCE_PATHS],
            )
        ],
        user_help=[
            _help(
                "skill_sources_missing",
                "Restore the repository checkout or rerun from a complete OpenYggdrasil clone.",
                "The provider must not invent missing runtime contracts or attachment tools.",
            )
        ],
    )


def _provider_deploy_route_check(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    install_surface: str,
) -> dict[str, Any]:
    if install_surface == "hermes_profile_skill" and provider_id == "hermes":
        destination = (
            f"~/.hermes/profiles/{provider_profile}/skills/"
            "autonomous-ai-agents/openyggdrasil-foreground-probe/SKILL.md"
        )
        return _check(
            check_id="provider.skill.deploy_route",
            label="Provider-native skill deploy route is supported",
            blocking=False,
            attempts=[
                _attempt(
                    route_id="hermes_profile_skill_route",
                    attempt_index=1,
                    max_attempts=1,
                    status="pass",
                    reason_code="hermes_profile_skill_route_supported",
                    comment=f"Hermes profile skill deploy route is available: {destination}",
                    evidence_refs=[_evidence("provider_surface", destination)],
                )
            ],
        )
    try:
        plan = build_deploy_plan(workspace_root=workspace_root, provider_ids=[provider_id])
        destination = plan[0].destination
    except Exception as exc:  # noqa: BLE001
        return _check(
            check_id="provider.skill.deploy_route",
            label="Provider-native skill deploy route is supported",
            blocking=False,
            attempts=[
                _attempt(
                    route_id="deploy_plan",
                    attempt_index=1,
                    max_attempts=1,
                    status="fail",
                    reason_code="provider_deploy_route_unsupported",
                    comment=f"No provider-native deploy route for provider_id={provider_id}: {exc}",
                    evidence_refs=[_evidence("runtime_probe", "runtime/attachments/deploy_skill.py")],
                )
            ],
            user_help=[
                _help(
                    "provider_deploy_route_unsupported",
                    "Use a supported provider id or add an explicit provider-native deploy target before relying on automatic install.",
                    "Provider install paths are provider-specific and cannot be guessed safely.",
                )
            ],
        )
    return _check(
        check_id="provider.skill.deploy_route",
        label="Provider-native skill deploy route is supported",
        blocking=False,
        attempts=[
            _attempt(
                route_id="deploy_plan",
                attempt_index=1,
                max_attempts=1,
                status="pass",
                reason_code="provider_deploy_route_supported",
                comment=f"Provider-native deploy route is available: {destination}",
                evidence_refs=[_evidence("local_file", str(destination))],
            )
        ],
    )


def _python_runtime_check() -> dict[str, Any]:
    ok = sys.version_info >= (3, 11)
    return _check(
        check_id="python.runtime.available",
        label="Python runtime can execute OpenYggdrasil probes",
        blocking=True,
        attempts=[
            _attempt(
                route_id="current_python",
                attempt_index=1,
                max_attempts=1,
                status="pass" if ok else "fail",
                reason_code="python_runtime_supported" if ok else "python_runtime_too_old",
                comment=(
                    f"Python runtime is supported: {sys.version.split()[0]} at {sys.executable}"
                    if ok
                    else f"Python 3.11+ is required; current runtime is {sys.version.split()[0]}"
                ),
                evidence_refs=[_evidence("runtime_probe", sys.executable, sys.version.split()[0])],
            )
        ],
        user_help=[
            _help(
                "python_runtime_too_old",
                "Install or select Python 3.11+ for the provider-side OpenYggdrasil runtime probes.",
                "Schema validation and runtime probes are Python-backed.",
            )
        ],
    )


def _attachment_bootstrap_check(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    try:
        proof = prove_provider_bootstrap_contract(
            workspace_root=workspace_root,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        )
        attempts.append(
            _attempt(
                route_id="provider_bootstrap_contract",
                attempt_index=1,
                max_attempts=2,
                status="pass" if proof["ok"] else "fail",
                reason_code="bootstrap_contract_passed" if proof["ok"] else "bootstrap_contract_failed",
                comment=(
                    "Provider bootstrap contract smoke passed."
                    if proof["ok"]
                    else f"Provider bootstrap contract smoke returned failing checks: {proof['checks']}"
                ),
                evidence_refs=[_evidence("runtime_probe", "runtime/attachments/bootstrap_contract.py")],
            )
        )
        if proof["ok"]:
            return _check(
                check_id="attachment.bootstrap.smoke",
                label="Provider attachment bootstrap can create session-bound artifacts",
                blocking=True,
                attempts=attempts,
            )
    except Exception as exc:  # noqa: BLE001
        attempts.append(
            _attempt(
                route_id="provider_bootstrap_contract",
                attempt_index=1,
                max_attempts=2,
                status="fail",
                reason_code="bootstrap_contract_exception",
                comment=f"Provider bootstrap contract smoke raised {exc.__class__.__name__}: {exc}",
                evidence_refs=[_evidence("runtime_probe", "runtime/attachments/bootstrap_contract.py")],
            )
        )

    try:
        bootstrap_skill_provider_session(
            workspace_root=workspace_root,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
            origin_kind="provider-thread",
            origin_locator={
                "provider_id": provider_id,
                "provider_profile": provider_profile,
                "provider_session_id": provider_session_id,
                "route": "cold_start_fallback_scaffold",
            },
        )
        validate_report = validate_workspace(workspace_root)
        ok = validate_report["error_count"] == 0
        attempts.append(
            _attempt(
                route_id="fallback_attachment_scaffold",
                attempt_index=2,
                max_attempts=2,
                status="pass" if ok else "fail",
                reason_code="fallback_scaffold_valid" if ok else "fallback_scaffold_invalid",
                comment=(
                    "Fallback attachment scaffold validated successfully."
                    if ok
                    else f"Fallback attachment scaffold validation errors={validate_report['error_count']}"
                ),
                evidence_refs=[_evidence("runtime_probe", "runtime/attachments/provider_attachment.py")],
            )
        )
    except Exception as exc:  # noqa: BLE001
        attempts.append(
            _attempt(
                route_id="fallback_attachment_scaffold",
                attempt_index=2,
                max_attempts=2,
                status="fail",
                reason_code="fallback_scaffold_exception",
                comment=f"Fallback attachment scaffold raised {exc.__class__.__name__}: {exc}",
                evidence_refs=[_evidence("runtime_probe", "runtime/attachments/provider_attachment.py")],
            )
        )

    return _check(
        check_id="attachment.bootstrap.smoke",
        label="Provider attachment bootstrap can create session-bound artifacts",
        blocking=True,
        attempts=attempts,
        user_help=[
            _help(
                "fallback_scaffold_invalid",
                "Run attachment repair or remove corrupted .yggdrasil provider artifacts after backing them up.",
                "The provider tried the canonical bootstrap route and the fallback scaffold route but still produced invalid runtime state.",
            )
        ],
    )


def _attachment_validation_check(workspace_root: Path) -> dict[str, Any]:
    try:
        report = validate_workspace(workspace_root)
        ok = report["error_count"] == 0
        comment = (
            f"Attachment validation passed for {report['attachment_count']} attachment(s)."
            if ok
            else f"Attachment validation found {report['error_count']} error(s)."
        )
    except Exception as exc:  # noqa: BLE001
        ok = False
        comment = f"Attachment validation raised {exc.__class__.__name__}: {exc}"
    return _check(
        check_id="attachment.validation",
        label="Generated attachment artifacts validate",
        blocking=True,
        attempts=[
            _attempt(
                route_id="validate_attachment",
                attempt_index=1,
                max_attempts=1,
                status="pass" if ok else "fail",
                reason_code="attachment_validation_passed" if ok else "attachment_validation_failed",
                comment=comment,
                evidence_refs=[_evidence("runtime_probe", "runtime/attachments/validate_attachment.py")],
            )
        ],
        user_help=[
            _help(
                "attachment_validation_failed",
                "Run runtime/attachments/repair_attachment.py or inspect the invalid .yggdrasil provider artifacts.",
                "OpenYggdrasil must reject corrupted or schema-incompatible provider state.",
            )
        ],
    )


def _reasoning_effort_contracts_check(workspace_root: Path) -> dict[str, Any]:
    missing = [path for path in MODULE_EFFORT_PATHS if not (workspace_root / path).exists()]
    return _check(
        check_id="reasoning.effort_contracts.present",
        label="Reasoning effort contracts are present",
        blocking=False,
        attempts=[
            _attempt(
                route_id="module_effort_inventory",
                attempt_index=1,
                max_attempts=1,
                status="pass" if not missing else "fail",
                reason_code="module_effort_contracts_present" if not missing else "module_effort_contracts_missing",
                comment=(
                    "Module effort requirement and split lease plan contracts are present."
                    if not missing
                    else "Missing module effort contract files: "
                    + ", ".join(path.as_posix() for path in missing)
                ),
                evidence_refs=[_evidence("local_file", (workspace_root / path).as_posix()) for path in MODULE_EFFORT_PATHS],
            )
        ],
        user_help=[
            _help(
                "module_effort_contracts_missing",
                "Restore the module effort schemas/runtime planner before enabling reasoning lease supply.",
                "The provider must know which modules require high, medium, or no reasoning before it can budget inference.",
            )
        ],
    )


def _linux_command_available(
    command: str,
    *,
    target_environment: str,
    command_runner: CommandRunner,
    which: Which,
) -> bool:
    if target_environment == "wsl2_linux" and platform.system().lower() == "windows":
        if which("wsl.exe") is None and which("wsl") is None:
            return False
        return command_runner(["wsl.exe", "sh", "-lc", f"command -v {command}"], 20)[0] == 0
    return which(command) is not None


def _sandbox_runtime_check(
    *,
    target_environment: str,
    sandbox_required_for_reasoning: bool,
    command_runner: CommandRunner,
    which: Which,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    if not sandbox_required_for_reasoning:
        attempts.append(
            _attempt(
                route_id="sandbox_not_required",
                attempt_index=1,
                max_attempts=1,
                status="pass",
                reason_code="sandbox_not_required_for_current_install",
                comment="Sandbox runtime is not required for this cold-start check.",
                evidence_refs=[_evidence("runtime_probe", "runtime/reasoning/process_sandbox_policy.py")],
            )
        )
        return _check(
            check_id="sandbox.runtime.available",
            label="Sandbox runtime target is available",
            blocking=False,
            attempts=attempts,
        )
    if target_environment == "native_windows_deferred":
        attempts.append(
            _attempt(
                route_id="native_windows_policy",
                attempt_index=1,
                max_attempts=1,
                status="fail",
                reason_code="native_windows_sandbox_deferred",
                comment="Native Windows sandbox execution is deferred; WSL2/Linux is the active target.",
                evidence_refs=[_evidence("runtime_probe", "runtime/reasoning/process_sandbox_policy.py")],
            )
        )
        return _check(
            check_id="sandbox.runtime.available",
            label="Sandbox runtime target is available",
            blocking=False,
            attempts=attempts,
            user_help=[
                _help(
                    "native_windows_sandbox_deferred",
                    "Run provider-side reasoning workers from WSL2/Linux until native Windows support is implemented.",
                    "The repo policy is Linux-first for sandboxed process execution.",
                )
            ],
        )

    if target_environment == "wsl2_linux" and platform.system().lower() == "windows":
        wsl_present = which("wsl.exe") is not None or which("wsl") is not None
        if wsl_present:
            code, stdout, stderr = command_runner(["wsl.exe", "sh", "-lc", "uname -a"], 20)
            target_ok = code == 0
            detail = stdout.strip() or stderr.strip() or None
        else:
            target_ok = False
            detail = "wsl.exe not found"
    else:
        target_ok = platform.system().lower() in {"linux", "darwin"}
        detail = platform.platform()

    attempts.append(
        _attempt(
            route_id="target_kernel_probe",
            attempt_index=1,
            max_attempts=2,
            status="pass" if target_ok else "fail",
            reason_code="sandbox_target_available" if target_ok else "sandbox_target_unavailable",
            comment=(
                f"Sandbox target environment is reachable: {detail}"
                if target_ok
                else f"Sandbox target environment is not reachable: {detail}"
            ),
            evidence_refs=[_evidence("runtime_probe", target_environment, detail)],
        )
    )
    if not target_ok:
        return _check(
            check_id="sandbox.runtime.available",
            label="Sandbox runtime target is available",
            blocking=False,
            attempts=attempts,
            user_help=[
                _help(
                    "sandbox_target_unavailable",
                    "Enable WSL2/Linux or run the provider worker in a Linux environment.",
                    "Sandboxed reasoning workers require the Linux-first runtime target.",
                )
            ],
        )

    missing = [
        command
        for command in ("bwrap", "socat")
        if not _linux_command_available(
            command,
            target_environment=target_environment,
            command_runner=command_runner,
            which=which,
        )
    ]
    attempts.append(
        _attempt(
            route_id="bubblewrap_dependency_probe",
            attempt_index=2,
            max_attempts=2,
            status="pass" if not missing else "fail",
            reason_code="sandbox_dependencies_present" if not missing else "sandbox_dependencies_missing",
            comment=(
                "Bubblewrap sandbox dependencies are present."
                if not missing
                else "Missing sandbox dependencies: " + ", ".join(missing)
            ),
            evidence_refs=[_evidence("runtime_probe", "bubblewrap+socat", None if not missing else ",".join(missing))],
        )
    )
    return _check(
        check_id="sandbox.runtime.available",
        label="Sandbox runtime target is available",
        blocking=False,
        attempts=attempts,
        user_help=[
            _help(
                "sandbox_dependencies_missing",
                "Install bubblewrap and socat inside the WSL2/Linux environment used by provider workers.",
                "OpenYggdrasil can attach memory without them, but sandboxed reasoning lease execution should fail closed.",
            )
        ],
    )


def _aggregate(check_results: list[dict[str, Any]]) -> tuple[str, bool, dict[str, Any], list[dict[str, str]], str, str]:
    failed = [row for row in check_results if row["status"] == "fail"]
    blocking_failed = [row for row in failed if row["blocking"]]
    user_help: list[dict[str, str]] = []
    for row in failed:
        user_help.extend(row["user_help"])

    if blocking_failed:
        status = "not_ready"
        admission_allowed = False
        next_action = "manual_user_action" if user_help else "stop_not_supported"
    elif failed:
        status = "degraded"
        admission_allowed = True
        next_action = "install_missing_dependency" if user_help else "start_attachment_bootstrap"
    else:
        status = "ready"
        admission_allowed = True
        next_action = "start_attachment_bootstrap"

    total_attempts = sum(len(row["attempts"]) for row in check_results)
    max_attempts = max(len(row["attempts"]) for row in check_results)
    failed_ids = [row["check_id"] for row in failed]
    alternate_routes_tried = any(len(row["attempts"]) > 1 for row in check_results)
    if status == "ready":
        final_comment = "Cold-start healthcheck passed; the provider can attach and continue with session bootstrap."
        provider_comment = final_comment
    elif status == "degraded":
        final_comment = (
            "Cold-start healthcheck can attach the provider, but one or more non-blocking runtime capabilities need user help."
        )
        provider_comment = final_comment + " See user_help for exact remediation."
    else:
        final_comment = (
            "Cold-start healthcheck cannot safely attach the provider in this environment after the available retry routes."
        )
        provider_comment = final_comment + " See failed_check_ids and user_help for the concrete environment issue."

    retry_summary = {
        "total_attempts": total_attempts,
        "max_attempts_per_check": max_attempts,
        "alternate_routes_tried": alternate_routes_tried,
        "failed_check_ids": failed_ids,
        "user_help_required": bool(user_help),
        "final_failure_comment": final_comment,
    }
    return status, admission_allowed, retry_summary, user_help, provider_comment, next_action


def run_provider_cold_start_healthcheck(
    *,
    workspace_root: Path = PROJECT_ROOT,
    provider_id: str,
    provider_profile: str = "default",
    provider_session_id: str = "cold-start-healthcheck",
    install_surface: str = "provider_native_skill",
    target_environment: str = "wsl2_linux",
    sandbox_required_for_reasoning: bool = True,
    force: bool = False,
    write_marker: bool = True,
    command_runner: CommandRunner = _run_command,
    which: Which = shutil.which,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    marker_path = marker_path_for(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    if marker_path.exists() and not force:
        cached = json.loads(marker_path.read_text(encoding="utf-8"))
        cached["run_mode"] = "cached"
        cached["run_once"]["previous_marker_found"] = True
        cached["run_once"]["marker_written"] = False
        validate_provider_cold_start_healthcheck(cached)
        return cached

    check_results = [
        _workspace_exists_check(workspace_root),
        _workspace_writable_check(workspace_root),
        _source_files_check(workspace_root),
        _provider_deploy_route_check(
            workspace_root=workspace_root,
            provider_id=provider_id,
            provider_profile=provider_profile,
            install_surface=install_surface,
        ),
        _python_runtime_check(),
        _attachment_bootstrap_check(
            workspace_root=workspace_root,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        ),
        _attachment_validation_check(workspace_root),
        _reasoning_effort_contracts_check(workspace_root),
        _sandbox_runtime_check(
            target_environment=target_environment,
            sandbox_required_for_reasoning=sandbox_required_for_reasoning,
            command_runner=command_runner,
            which=which,
        ),
    ]
    status, admission_allowed, retry_summary, user_help, provider_comment, next_action = _aggregate(check_results)
    payload = {
        "schema_version": "provider_cold_start_healthcheck.v1",
        "healthcheck_id": uuid.uuid4().hex,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "workspace_root": str(workspace_root),
        "install_surface": install_surface,
        "run_mode": "forced_recheck" if force else "first_install",
        "status": status,
        "admission_allowed": admission_allowed,
        "check_results": check_results,
        "retry_summary": retry_summary,
        "run_once": {
            "marker_path": str(marker_path),
            "marker_written": write_marker,
            "previous_marker_found": False,
        },
        "sandbox_policy": {
            "target_environment": target_environment,
            "required_for_reasoning": sandbox_required_for_reasoning,
            "backend_preference": list(DEFAULT_BACKEND_PREFERENCE),
        },
        "provider_comment": provider_comment,
        "user_help_required": bool(user_help),
        "user_help": user_help,
        "next_action": next_action,
        "created_at": utc_now_iso(),
    }
    validate_provider_cold_start_healthcheck(payload)
    if write_marker:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
