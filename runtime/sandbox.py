"""
Reasoning Lease Sandbox — 14차 Axis 4: bubblewrap 기반 샌드박스.

Usage:
    from runtime.sandbox import sandbox_run
    result = sandbox_run(["python", "-c", "print('hello')"])
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BWRAP = "bwrap" if os.name != "nt" else None


def _find_bwrap() -> str | None:
    """bubblewrap 바이너리 경로 탐색."""
    if os.name == "nt":
        return None
    path = shutil.which("bwrap")
    if path:
        return path
    for candidate in ["/usr/bin/bwrap", "/usr/local/bin/bwrap"]:
        if Path(candidate).exists():
            return candidate
    return None


def sandbox_run(
    cmd: list[str],
    *,
    read_only_paths: list[str] | None = None,
    tmp_dir: str | None = None,
    timeout: int = 300,
) -> dict:
    """
    bubblewrap 샌드박스에서 명령 실행.

    Args:
        cmd: 실행할 명령어 리스트
        read_only_paths: 읽기 전용 마운트 경로 목록
        tmp_dir: 임시 쓰기 가능 디렉토리
        timeout: 제한 시간(초)

    Returns:
        {"status": "ok"|"error", "stdout": str, "stderr": str, "exit_code": int}
    """
    bwrap = _find_bwrap()

    if bwrap is None:
        # WSL/Windows: bubblewrap 불가 → 경량 fallback
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "status": "ok" if result.returncode == 0 else "error",
                "stdout": result.stdout[:10000],
                "stderr": result.stderr[:10000],
                "exit_code": result.returncode,
                "sandbox": "none",
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "stdout": "", "stderr": "timeout", "exit_code": -1, "sandbox": "none"}

    # bubblewrap 모드
    bwrap_cmd = [
        bwrap,
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--proc", "/proc",
        "--dev", "/dev",
        "--unshare-all",
        "--die-with-parent",
    ]

    if read_only_paths:
        for rp in read_only_paths:
            if Path(rp).exists():
                bwrap_cmd.extend(["--ro-bind", rp, rp])

    if tmp_dir:
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)
        bwrap_cmd.extend(["--tmpfs", "/tmp"])
        bwrap_cmd.extend(["--bind", tmp_dir, "/tmp"])

    bwrap_cmd.extend(cmd)

    try:
        result = subprocess.run(bwrap_cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[:10000],
            "stderr": result.stderr[:10000],
            "exit_code": result.returncode,
            "sandbox": "bubblewrap",
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "stdout": "", "stderr": "timeout", "exit_code": -1, "sandbox": "bubblewrap"}
    except FileNotFoundError:
        return {"status": "error", "stdout": "", "stderr": "bwrap not found", "exit_code": -1, "sandbox": "none"}
