"""PTC sandbox executor.

The executor has two surfaces:

- ``ipc``: worker-authored code can call host primitives through a Unix socket.
- ``batch``: worker-authored code runs against copied runtime/vault files.

Only the IPC path can enforce per-caller primitive allowlists. Both paths must
report an execution lease and must not silently relabel an unsandboxed
subprocess fallback as a successful sandboxed execution.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from runtime.ptc.ipc_server import PTCIpcServer, allowed_methods_for_caller
from runtime.ptc.stub_generator import generate_ptc_code


PTC_EXECUTION_LEASE_SCHEMA_VERSION = "ptc_execution_lease.v1"


def _build_execution_lease(
    *,
    mode: str,
    caller: str,
    allowed_methods: Iterable[str] | None,
    timeout: int,
    sandbox_status: str,
    allow_unsafe_subprocess_fallback: bool,
    caller_enforced_by_ipc: bool,
) -> dict[str, Any]:
    return {
        "schema_version": PTC_EXECUTION_LEASE_SCHEMA_VERSION,
        "mode": mode,
        "caller": caller,
        "allowed_methods": sorted(allowed_methods_for_caller(caller, allowed_methods)),
        "timeout_seconds": timeout,
        "sandbox_required": True,
        "sandbox_status": sandbox_status,
        "caller_enforced_by_ipc": caller_enforced_by_ipc,
        "unsafe_subprocess_fallback_allowed": bool(allow_unsafe_subprocess_fallback),
        "raw_provider_material_included": False,
        "fabricated_answer": False,
    }


def _with_execution_lease(result: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    payload["ptc_execution_lease"] = lease
    return payload


def _sandbox_unavailable_result(*, lease: dict[str, Any]) -> dict[str, Any]:
    return _with_execution_lease(
        {
            "status": "typed_unavailable",
            "stdout": "",
            "stderr": "bubblewrap sandbox unavailable",
            "exit_code": -1,
            "sandbox": "unavailable",
            "typed_unavailable": {
                "schema_version": "typed_unavailable.v1",
                "status": "typed_unavailable",
                "reason_code": "ptc_sandbox_unavailable",
                "blocked_stage": "ptc_code_execution",
                "user_help": "Install bubblewrap or use the bounded JSON PTC runtime path.",
                "raw_provider_material_included": False,
                "fabricated_answer": False,
            },
        },
        lease,
    )


def _run_unsafe_subprocess(
    *,
    code_path: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["python3", str(code_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[:10000],
            "stderr": result.stderr[:10000],
            "exit_code": result.returncode,
            "sandbox": "none",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "timeout",
            "exit_code": -1,
            "sandbox": "none",
        }


def execute_ptc_code(
    code: str,
    vault: Path,
    *,
    runtime_dir: Path | None = None,
    timeout: int = 120,
    mode: str = "ipc",
    caller: str = "legacy_compat",
    allowed_methods: Iterable[str] | None = None,
    allow_unsafe_subprocess_fallback: bool = False,
) -> dict[str, Any]:
    """Run worker-authored Python through the bounded PTC execution surface."""
    if runtime_dir is None:
        runtime_dir = Path(__file__).resolve().parent.parent

    if mode == "ipc":
        return _execute_ipc(
            code,
            vault,
            runtime_dir,
            timeout,
            caller=caller,
            allowed_methods=allowed_methods,
            allow_unsafe_subprocess_fallback=allow_unsafe_subprocess_fallback,
        )
    return _execute_batch(
        code,
        vault,
        runtime_dir,
        timeout,
        caller=caller,
        allowed_methods=allowed_methods,
        allow_unsafe_subprocess_fallback=allow_unsafe_subprocess_fallback,
    )


def _execute_ipc(
    code: str,
    vault: Path,
    runtime_dir: Path,
    timeout: int,
    *,
    caller: str,
    allowed_methods: Iterable[str] | None,
    allow_unsafe_subprocess_fallback: bool,
) -> dict[str, Any]:
    from runtime.sandbox import sandbox_run

    tmp_dir = Path(tempfile.mkdtemp(prefix="ptc_ipc_"))
    socket_path = str(tmp_dir / "ptc.sock")
    server: PTCIpcServer | None = None

    try:
        config = {"vault": str(vault), "runtime": str(runtime_dir), "mode": "ipc"}
        (tmp_dir / "ptc_config.json").write_text(json.dumps(config), encoding="utf-8")
        code_path = tmp_dir / "ptc_code.py"
        code_path.write_text(generate_ptc_code(code, mode="ipc"), encoding="utf-8")

        server = PTCIpcServer(
            socket_path,
            vault,
            timeout=timeout,
            caller=caller,
            allowed_methods=allowed_methods,
        )
        server.start()

        result = sandbox_run(
            cmd=["python3", "/tmp/ptc_code.py"],
            read_only_paths=None,
            tmp_dir=str(tmp_dir),
            timeout=timeout,
        )
        lease = _build_execution_lease(
            mode="ipc",
            caller=caller,
            allowed_methods=allowed_methods,
            timeout=timeout,
            sandbox_status="bubblewrap" if result is not None else "unavailable",
            allow_unsafe_subprocess_fallback=allow_unsafe_subprocess_fallback,
            caller_enforced_by_ipc=True,
        )
        if result is None:
            if not allow_unsafe_subprocess_fallback:
                return _sandbox_unavailable_result(lease=lease)
            result = _run_unsafe_subprocess(
                code_path=code_path,
                timeout=timeout,
                env={**os.environ, "PYTHONPATH": str(runtime_dir.parent)},
            )
            lease = _build_execution_lease(
                mode="ipc",
                caller=caller,
                allowed_methods=allowed_methods,
                timeout=timeout,
                sandbox_status="none",
                allow_unsafe_subprocess_fallback=allow_unsafe_subprocess_fallback,
                caller_enforced_by_ipc=True,
            )
        return _with_execution_lease(result, lease)
    finally:
        if server is not None:
            server.stop()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _execute_batch(
    code: str,
    vault: Path,
    runtime_dir: Path,
    timeout: int,
    *,
    caller: str,
    allowed_methods: Iterable[str] | None,
    allow_unsafe_subprocess_fallback: bool,
) -> dict[str, Any]:
    from runtime.sandbox import sandbox_run

    tmp_dir = Path(tempfile.mkdtemp(prefix="ptc_sandbox_"))
    try:
        vault_in_sandbox = tmp_dir / "vault"
        if vault.exists():
            shutil.copytree(
                vault,
                vault_in_sandbox,
                symlinks=True,
                dirs_exist_ok=True,
                ignore_dangling_symlinks=True,
            )

        runtime_in_sandbox = tmp_dir / "runtime"
        shutil.copytree(
            runtime_dir,
            runtime_in_sandbox,
            symlinks=False,
            dirs_exist_ok=True,
            ignore_dangling_symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

        config = {"vault": "/tmp/vault", "runtime": "/tmp/runtime"}
        (tmp_dir / "ptc_config.json").write_text(json.dumps(config), encoding="utf-8")
        code_path = tmp_dir / "ptc_code.py"
        code_path.write_text(generate_ptc_code(code, mode="batch"), encoding="utf-8")

        result = sandbox_run(
            cmd=["python3", "/tmp/ptc_code.py"],
            read_only_paths=None,
            tmp_dir=str(tmp_dir),
            timeout=timeout,
        )
        lease = _build_execution_lease(
            mode="batch",
            caller=caller,
            allowed_methods=allowed_methods,
            timeout=timeout,
            sandbox_status="bubblewrap" if result is not None else "unavailable",
            allow_unsafe_subprocess_fallback=allow_unsafe_subprocess_fallback,
            caller_enforced_by_ipc=False,
        )
        if result is None:
            if not allow_unsafe_subprocess_fallback:
                return _sandbox_unavailable_result(lease=lease)
            result = _run_unsafe_subprocess(code_path=code_path, timeout=timeout)
            lease = _build_execution_lease(
                mode="batch",
                caller=caller,
                allowed_methods=allowed_methods,
                timeout=timeout,
                sandbox_status="none",
                allow_unsafe_subprocess_fallback=allow_unsafe_subprocess_fallback,
                caller_enforced_by_ipc=False,
            )
        return _with_execution_lease(result, lease)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


__all__ = [
    "PTC_EXECUTION_LEASE_SCHEMA_VERSION",
    "execute_ptc_code",
]
