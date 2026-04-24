from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from harness_common import DEFAULT_HERMES_BIN


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY_SECONDS = 1.0
MAX_PACKET_FACTS = 5
MAX_PACKETS = 3


def build_answer_state(*, packets: list[dict], query_text: str) -> dict[str, Any]:
    packet_summaries: list[dict[str, Any]] = []
    for packet in packets[:MAX_PACKETS]:
        payload = packet.get("payload", {})
        packet_summaries.append(
            {
                "packet_id": packet.get("message_id"),
                "message_type": packet.get("message_type"),
                "topic": packet.get("scope", {}).get("topic"),
                "facts": list(payload.get("facts", []))[:MAX_PACKET_FACTS],
                "source_paths": list(payload.get("source_paths", []))[:MAX_PACKET_FACTS],
            }
        )
    return {
        "question": query_text,
        "packet_count": len(packets),
        "packet_summaries": packet_summaries,
    }


def build_answer_prompt(*, query_text: str, state: dict[str, Any]) -> str:
    state_json = json.dumps(state, ensure_ascii=False, indent=2)
    return (
        "You are Hermes answering the user's question using plugin-plane support context.\n"
        "Write the final answer directly to the user.\n"
        "Use the selected packet facts when relevant.\n"
        "Do not mention packets, mailboxes, telemetry, or internal logging.\n"
        "Do not invent missing support. If the support is insufficient, answer conservatively and say what remains uncertain.\n\n"
        f"User question:\n{query_text}\n\n"
        f"Support context:\n{state_json}\n"
    )


def render_answer_via_hermes(
    *,
    query_text: str,
    state: dict[str, Any],
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> str:
    prompt = build_answer_prompt(query_text=query_text, state=state)
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
                    "Hermes answer-edge rendering failed "
                    f"(returncode={completed.returncode})"
                )
            answer = last_stdout.strip()
            if not answer:
                raise ValueError("Hermes answer-edge renderer returned empty output")
            return answer
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))

    raise RuntimeError(
        "Hermes answer-edge rendering failed after retries\n"
        f"last_error={last_error!r}\n"
        f"stdout_preview={last_stdout[:800]!r}\n"
        f"stderr_preview={last_stderr[:800]!r}"
    )


def _run_wsl_python(python_code: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("wsl") is None:
        raise RuntimeError("wsl command is not available")
    return subprocess.run(
        ["wsl", "-d", "ubuntu-agent", "--", "python3", "-c", python_code],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )


def render_fallback_answer(*, query_text: str, state: dict[str, Any]) -> str:
    packet_count = int(state.get("packet_count") or 0)
    if packet_count <= 0:
        return (
            "I do not have any packet-backed support context yet, so I can only answer conservatively. "
            "I would start from the Graphify query surface and then verify against linked SOT notes."
        )
    first_packet = next(iter(state.get("packet_summaries") or []), {})
    topic = first_packet.get("topic") or "the current topic"
    facts = first_packet.get("facts") or []
    fact_text = "; ".join(str(fact) for fact in facts[:2]) if facts else "support context is available"
    return f"For your question about {topic}, the current support suggests that {fact_text}."


def render_answer_payload(
    *,
    packets: list[dict],
    query_text: str,
    renderer: Callable[..., str] | None = None,
) -> dict[str, Any]:
    state = build_answer_state(packets=packets, query_text=query_text)
    active_renderer = renderer or render_answer_via_hermes
    try:
        answer_text = active_renderer(query_text=query_text, state=state)
        rendering_mode = "hermes-answer-edge"
        render_error = None
    except Exception as exc:
        answer_text = render_fallback_answer(query_text=query_text, state=state)
        rendering_mode = "deterministic-fallback"
        render_error = str(exc)

    payload: dict[str, Any] = {
        "rendering_mode": rendering_mode,
        "answer_text": answer_text,
        "answer_hash": "sha256:" + hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
        "state": state,
    }
    if render_error:
        payload["render_error"] = render_error
    return payload
