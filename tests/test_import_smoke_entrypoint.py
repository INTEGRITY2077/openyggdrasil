from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_smoke(*args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return json.loads(completed.stdout)


def test_import_smoke_direct_entrypoint_runs_from_readme_command() -> None:
    payload = _run_smoke("runtime/import_smoke.py")

    assert payload["ok"] is True
    assert payload["failed_count"] == 0


def test_import_smoke_module_entrypoint_runs_from_repo_root() -> None:
    payload = _run_smoke("-m", "runtime.import_smoke")

    assert payload["ok"] is True
    assert payload["failed_count"] == 0
