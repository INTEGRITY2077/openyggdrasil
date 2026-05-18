from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile


WORKER_JUDGMENT_PAYLOAD_TOKENS = (
    "[MS1",
    "[MF1",
    "작업 결과",
    "support_facts",
    "judgment",
    "quality_assessment.verdict",
)


@dataclass(frozen=True)
class TmuxSendResult:
    ok: bool
    target: str
    reason: str
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _run_tmux(args: list[str], *, target: str, reason: str, timeout: float = 5.0) -> TmuxSendResult:
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return TmuxSendResult(
            ok=False,
            target=target,
            reason=reason,
            returncode=1,
            stderr=f"{type(exc).__name__}: {exc}",
        )
    return TmuxSendResult(
        ok=result.returncode == 0,
        target=target,
        reason=reason,
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


def validate_no_worker_judgment_payload(text: str) -> None:
    lowered = str(text or "").lower()
    for token in WORKER_JUDGMENT_PAYLOAD_TOKENS:
        if token.lower() in lowered:
            raise ValueError("Postman/tmux lane payload must not inject worker judgment material")


def send_enter(target: str, *, reason: str) -> TmuxSendResult:
    return _run_tmux(["send-keys", "-t", target, "Enter"], target=target, reason=reason)


def cancel_prompt(target: str, *, reason: str) -> TmuxSendResult:
    return _run_tmux(["send-keys", "-t", target, "-X", "cancel"], target=target, reason=reason)


def wake_lane(target: str, *, reason: str) -> TmuxSendResult:
    return send_enter(target, reason=reason)


def paste_text_enter(
    target: str,
    text: str,
    *,
    reason: str,
    cancel_existing_prompt: bool = False,
    validate_worker_payload: bool = False,
    timeout: float = 5.0,
) -> TmuxSendResult:
    if validate_worker_payload:
        validate_no_worker_judgment_payload(text)
    if cancel_existing_prompt:
        cancelled = cancel_prompt(target, reason=f"{reason}:cancel")
        if not cancelled.ok:
            return cancelled
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", delete=False) as temp_file:
            temp_file.write(text)
            temp_path = Path(temp_file.name)
        loaded = _run_tmux(
            ["load-buffer", str(temp_path)],
            target=target,
            reason=f"{reason}:load_buffer",
            timeout=timeout,
        )
        if not loaded.ok:
            return loaded
        pasted = _run_tmux(
            ["paste-buffer", "-t", target],
            target=target,
            reason=f"{reason}:paste",
            timeout=timeout,
        )
        if not pasted.ok:
            return pasted
        return send_enter(target, reason=f"{reason}:enter")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
