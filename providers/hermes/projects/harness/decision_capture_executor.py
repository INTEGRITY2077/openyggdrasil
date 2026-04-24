from __future__ import annotations

import base64
import time
from typing import Any, Callable, Dict, Mapping

from decision_distiller import (
    build_decision_distillation_prompt,
    distill_decision_candidate,
    extract_json_object,
    finalize_decision_candidate,
)
from packet_factory import build_decision_candidate_packet
from plugin_logger import record_plugin_event
from postman_gateway import submit_packet
from promotion_worthiness import (
    DEFAULT_HERMES_BIN,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    _run_wsl_python,
)


build_decision_capture_prompt = build_decision_distillation_prompt
_extract_json_object = extract_json_object


def render_decision_candidate_via_hermes(
    *,
    decision_surface: Mapping[str, Any],
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    prompt = build_decision_capture_prompt(decision_surface=decision_surface)
    encoded = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
    python_code = f"""
import base64, os, shutil, subprocess, sys
prompt = base64.b64decode('{encoded}').decode('utf-8')
candidate = os.path.expanduser(r'''{hermes_bin}''')
if os.path.exists(candidate):
    executable = candidate
else:
    executable = shutil.which(candidate) or shutil.which('hermes')
    if executable is None:
        fallback = os.path.expanduser('~/.local/bin/hermes')
        executable = fallback if os.path.exists(fallback) else candidate
cp = subprocess.run(
    [executable,'chat','-q',prompt,'-Q','--max-turns','{max_turns}'],
    text=True,
    capture_output=True,
)
sys.stdout.write(cp.stdout)
sys.stderr.write(cp.stderr)
raise SystemExit(cp.returncode)
""".strip()

    last_error: Exception | None = None
    last_stdout = ""
    last_stderr = ""
    for attempt in range(1, max(1, retries) + 1):
        completed = _run_wsl_python(python_code)
        last_stdout = completed.stdout or ""
        last_stderr = completed.stderr or ""
        try:
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Hermes decision capture failed (returncode={completed.returncode})"
                )
            return extract_json_object(last_stdout)
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))
    raise RuntimeError(
        "Hermes decision capture failed after retries\n"
        f"last_error={last_error!r}\n"
        f"stdout_preview={last_stdout[:800]!r}\n"
        f"stderr_preview={last_stderr[:800]!r}"
    )


def execute_decision_capture(
    *,
    profile: str,
    session_id: str | None,
    decision_surface: Mapping[str, Any],
    parent_question_id: str | None = None,
    mailbox_namespace: str | None = None,
    renderer: Callable[..., Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    if not session_id:
        raise RuntimeError("execute_decision_capture requires session_id")
    decision_candidate = distill_decision_candidate(
        decision_surface=decision_surface,
        renderer=renderer or render_decision_candidate_via_hermes,
        provider_id="hermes",
        profile=profile,
        session_id=session_id,
    )
    packet = build_decision_candidate_packet(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        decision_candidate=decision_candidate,
        producer="decision-capture-executor",
    )
    submit_packet(packet, namespace=mailbox_namespace)
    record_plugin_event(
        event_type="decision_candidate_generated",
        actor="decision_capture_executor",
        parent_question_id=parent_question_id,
        profile=profile,
        session_id=session_id,
        query_text=decision_candidate.get("surface_summary"),
        artifacts={
            "packet_id": packet["message_id"],
            "packet_type": packet["message_type"],
            "candidate_id": decision_candidate["candidate_id"],
            "mailbox_namespace": mailbox_namespace,
            "core_role": "decision_distiller",
        },
        state={
            "stability_state": decision_candidate["stability_state"],
            "confidence_score": decision_candidate["confidence_score"],
            "reason_labels": decision_candidate["reason_labels"],
            "topic_hint": decision_candidate["topic_hint"],
        },
    )
    return {"packet": packet, "decision_candidate": decision_candidate}


__all__ = [
    "build_decision_capture_prompt",
    "build_decision_distillation_prompt",
    "distill_decision_candidate",
    "execute_decision_capture",
    "extract_json_object",
    "finalize_decision_candidate",
    "render_decision_candidate_via_hermes",
]
