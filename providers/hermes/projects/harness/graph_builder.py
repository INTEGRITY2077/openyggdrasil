from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from graph_freshness import DEFAULT_GRAPH_SUMMARY_PATH, mark_graph_rebuild
from harness_common import file_lock
from worker_runtime import record_worker_event


PROJECTS_ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_SCRIPT = PROJECTS_ROOT / "graphify-poc" / "run_graphify_pipeline.py"
WSL_DISTRO = "ubuntu-agent"


def windows_to_wsl(path_value: str | Path) -> str:
    normalized = str(path_value).replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0].lower()
        tail = normalized[2:]
        if tail.startswith("/"):
            tail = tail[1:]
        return f"/mnt/{drive}/{tail}"
    return normalized


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def wsl_graphify_command(payload: Dict[str, Any]) -> List[str]:
    sandbox_root = payload["sandbox_root"]
    sandbox_root_wsl = windows_to_wsl(sandbox_root)
    graphify_script_wsl = windows_to_wsl(str(GRAPHIFY_SCRIPT))
    vault_wsl = windows_to_wsl(payload["vault"])
    manifest_wsl = windows_to_wsl(payload["manifest"])

    script_parts = [
        f"cd {shell_quote(sandbox_root_wsl)}",
        "&&",
        f"./.venv-wsl/bin/python {shell_quote(graphify_script_wsl)}",
        f"--vault {shell_quote(vault_wsl)}",
        f"--sandbox-root {shell_quote(sandbox_root_wsl)}",
        f"--manifest {shell_quote(manifest_wsl)}",
    ]
    if payload.get("refresh_semantic"):
        script_parts.append("--refresh-semantic")
    if payload.get("directed"):
        script_parts.append("--directed")
    bash_script = " ".join(script_parts)
    return ["wsl", "-d", WSL_DISTRO, "bash", "-lc", bash_script]


def run_subprocess(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def execute_graph_rebuild(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job["payload"]

    with file_lock("graph"):
        result = run_subprocess(wsl_graphify_command(payload))

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "graph rebuild failed"
        )

    record_worker_event(
        "graph_rebuild_completed",
        {
            "job_id": job["job_id"],
            "stdout": result.stdout.strip(),
        },
    )
    freshness = mark_graph_rebuild(
        job_id=job["job_id"],
        parent_question_id=job.get("parent_question_id"),
        summary_path=DEFAULT_GRAPH_SUMMARY_PATH,
    )
    record_worker_event(
        "graph_freshness_marked_fresh",
        {
            "job_id": job["job_id"],
            "freshness_status": freshness["status"],
            "reasons": freshness["reasons"],
        },
    )
    return {"stdout": result.stdout.strip()}
