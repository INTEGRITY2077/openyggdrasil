from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal


DEFAULT_WSL_DISTRO = "ubuntu-agent"


def run_wsl_python(
    python_code: str,
    *,
    timeout_seconds: int | None = None,
    cwd: Path | None = None,
    distro: str = DEFAULT_WSL_DISTRO,
    mode: Literal["command", "heredoc"] = "command",
) -> subprocess.CompletedProcess[str]:
    if shutil.which("wsl") is None:
        raise RuntimeError("wsl command is not available")

    if mode == "heredoc":
        script = "python3 - <<'PY'\n" + python_code + "\nPY"
        command = ["wsl", "-d", distro, "--", "bash", "-lc", script]
    else:
        command = ["wsl", "-d", distro, "--", "python3", "-c", python_code]

    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        cwd=str(cwd) if cwd else None,
    )
