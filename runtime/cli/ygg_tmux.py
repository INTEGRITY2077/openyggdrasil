from __future__ import annotations

import os
import subprocess
import sys

def _tmux(*args: str) -> subprocess.CompletedProcess:
    command = ["tmux", *args]
    try:
        return subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            command,
            127,
            stdout="",
            stderr="tmux executable not found",
        )

def _tmux_session_exists(session: str) -> bool:
    return _tmux("has-session", "-t", session).returncode == 0

def _inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))

def _tmux_attach_or_switch(session: str) -> None:
    """Attach from a normal shell; switch-client from an existing tmux client."""
    if _inside_tmux():
        result = _tmux("switch-client", "-t", session)
        if result.returncode != 0:
            print((result.stderr or result.stdout or f"tmux switch-client failed for {session}").strip())
            sys.exit(result.returncode)
        return
    try:
        os.execvp("tmux", ["tmux", "attach", "-t", session])
    except FileNotFoundError:
        print("typed_unavailable: tmux executable not found")
        sys.exit(127)


__all__ = [
    "_tmux",
    "_tmux_session_exists",
    "_inside_tmux",
    "_tmux_attach_or_switch",
]
