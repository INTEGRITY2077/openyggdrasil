"""
PTC Sandbox Executor — 14차 Axis 4: LLM 코드를 bubblewrap 샌드박스에서 실행.

Two modes:
  batch: vault + runtime 복사 → bwrap → 1회 실행 → 결과 수집
  ipc:   Unix Domain Socket → LLM 코드가 IPC 콜백으로 primitives 호출

IPC 콜백 루프는 capability stub + host callback 패턴을
bwrap + Unix Domain Socket으로 구현한 것이다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from runtime.ptc.stub_generator import generate_ptc_code


def execute_ptc_code(
    code: str,
    vault: Path,
    *,
    runtime_dir: Path | None = None,
    timeout: int = 120,
    mode: str = "ipc",
) -> dict:
    """LLM이 작성한 Python 코드를 bubblewrap 샌드박스에서 실행.

    Args:
        code: LLM이 작성한 Python 코드
        vault: Vault 디렉토리
        runtime_dir: runtime/ 디렉토리. 기본값은 sandbox_executor.py 기준.
        timeout: 실행 제한 시간(초)
        mode: "ipc" (Unix socket 콜백) 또는 "batch" (직접 import)

    Returns:
        {"status": "ok"|"error", "stdout": str, "stderr": str, "exit_code": int,
         "sandbox": "bubblewrap"|"none"}
    """
    if runtime_dir is None:
        runtime_dir = Path(__file__).resolve().parent.parent  # runtime/

    if mode == "ipc":
        return _execute_ipc(code, vault, runtime_dir, timeout)
    else:
        return _execute_batch(code, vault, runtime_dir, timeout)


def _execute_ipc(
    code: str,
    vault: Path,
    runtime_dir: Path,
    timeout: int,
) -> dict:
    """IPC 모드: Unix Domain Socket으로 LLM 코드 ↔ 호스트 양방향 통신.

    bwrap 내부에서는 /tmp/ptc.sock 으로 소켓에 접근한다.
    vault와 runtime은 호스트에 그대로 있고, IPC를 통해서만 접근한다.
    """
    from runtime.ptc.ipc_server import PTCIpcServer
    from runtime.sandbox import sandbox_run

    # 1. 임시 디렉토리 생성
    tmp_dir = Path(tempfile.mkdtemp(prefix="ptc_ipc_"))
    socket_path = str(tmp_dir / "ptc.sock")

    try:
        # 2. ptc_config.json (IPC 모드는 vault 경로만 참고용)
        config = {"vault": str(vault), "runtime": str(runtime_dir), "mode": "ipc"}
        (tmp_dir / "ptc_config.json").write_text(json.dumps(config), encoding="utf-8")

        # 3. IPC preamble + LLM 코드 합성 (stub_generator 사용)
        full_code = generate_ptc_code(code, mode="ipc")
        (tmp_dir / "ptc_code.py").write_text(full_code, encoding="utf-8")

        # 4. IPC 서버 시작 (백그라운드 스레드)
        server = PTCIpcServer(socket_path, vault, timeout=timeout)
        server.start()

        # 5. bwrap 실행 (tmp_dir가 /tmp로 마운트되므로 /tmp/ptc.sock 사용 가능)
        #    IPC 서버가 떠 있는 동안 bwrap 안의 코드가 소켓으로 콜백
        result = sandbox_run(
            cmd=["python3", "/tmp/ptc_code.py"],
            read_only_paths=None,
            tmp_dir=str(tmp_dir),
            timeout=timeout,
        )

        # 5b. bwrap 미설치 → subprocess 직접 실행 (격리 없음)
        if result is None:
            try:
                r = subprocess.run(
                    ["python3", str(tmp_dir / "ptc_code.py")],
                    capture_output=True, text=True, timeout=timeout,
                    env={**__import__('os').environ, "PYTHONPATH": str(runtime_dir.parent)},
                )
                result = {
                    "status": "ok" if r.returncode == 0 else "error",
                    "stdout": r.stdout[:10000], "stderr": r.stderr[:10000],
                    "exit_code": r.returncode, "sandbox": "none",
                }
            except subprocess.TimeoutExpired:
                result = {"status": "error", "stdout": "", "stderr": "timeout",
                          "exit_code": -1, "sandbox": "none"}

        # 6. 서버 정리
        server.stop()

        return result

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _execute_batch(
    code: str,
    vault: Path,
    runtime_dir: Path,
    timeout: int,
) -> dict:
    """Batch 모드: vault + runtime을 tmp_dir로 복사하여 1회 실행.

    IPC 없이 모든 것이 bwrap 내부에서 처리된다.
    """
    from runtime.sandbox import sandbox_run

    tmp_dir = Path(tempfile.mkdtemp(prefix="ptc_sandbox_"))

    try:
        # vault 복사
        vault_in_sandbox = tmp_dir / "vault"
        if vault.exists():
            shutil.copytree(vault, vault_in_sandbox, symlinks=True,
                          dirs_exist_ok=True, ignore_dangling_symlinks=True)

        # runtime 복사
        runtime_in_sandbox = tmp_dir / "runtime"
        shutil.copytree(runtime_dir, runtime_in_sandbox, symlinks=False,
                      dirs_exist_ok=True, ignore_dangling_symlinks=True,
                      ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        # config
        config = {"vault": "/tmp/vault", "runtime": "/tmp/runtime"}
        (tmp_dir / "ptc_config.json").write_text(json.dumps(config), encoding="utf-8")

        # batch preamble + LLM 코드
        full_code = generate_ptc_code(code, mode="batch")
        (tmp_dir / "ptc_code.py").write_text(full_code, encoding="utf-8")

        result = sandbox_run(
            cmd=["python3", "/tmp/ptc_code.py"],
            read_only_paths=None,
            tmp_dir=str(tmp_dir),
            timeout=timeout,
        )

        # bwrap 미설치 → subprocess 직접 실행 (격리 없음)
        if result is None:
            try:
                r = subprocess.run(
                    ["python3", str(tmp_dir / "ptc_code.py")],
                    capture_output=True, text=True, timeout=timeout,
                )
                result = {
                    "status": "ok" if r.returncode == 0 else "error",
                    "stdout": r.stdout[:10000], "stderr": r.stderr[:10000],
                    "exit_code": r.returncode, "sandbox": "none",
                }
            except subprocess.TimeoutExpired:
                result = {"status": "error", "stdout": "", "stderr": "timeout",
                          "exit_code": -1, "sandbox": "none"}

        return result

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
