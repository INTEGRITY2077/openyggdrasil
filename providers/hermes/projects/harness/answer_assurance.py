from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from answer_edge_renderer import build_answer_state
from harness_common import DEFAULT_HERMES_BIN


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RETRIES = 1
DEFAULT_RETRY_DELAY_SECONDS = 1.0


def build_assurance_prompt(
    *,
    query_text: str,
    state: dict[str, Any],
    initial_answer: str,
    quality_verdict: dict[str, Any],
) -> str:
    state_json = json.dumps(state, ensure_ascii=False, indent=2)
    verdict_json = json.dumps(quality_verdict, ensure_ascii=False, indent=2)
    return (
        "You are Hermes repairing an answer using plugin-plane support context.\n"
        "Rewrite the answer directly to the user.\n"
        "Use ONLY the support facts and topics from the structured context.\n"
        "Do not mention packets, mailboxes, telemetry, internal logging, or evaluation scores.\n"
        "Do not invent any support beyond the provided context.\n"
        "If the support is still insufficient, answer conservatively and state what remains uncertain.\n"
        "Keep the answer aligned with the user's question language.\n\n"
        f"User question:\n{query_text}\n\n"
        f"Initial answer:\n{initial_answer}\n\n"
        f"Support context:\n{state_json}\n\n"
        f"Quality verdict:\n{verdict_json}\n"
    )


def render_assurance_via_hermes(
    *,
    query_text: str,
    state: dict[str, Any],
    initial_answer: str,
    quality_verdict: dict[str, Any],
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> str:
    prompt = build_assurance_prompt(
        query_text=query_text,
        state=state,
        initial_answer=initial_answer,
        quality_verdict=quality_verdict,
    )
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
                    "Hermes answer assurance rendering failed "
                    f"(returncode={completed.returncode})"
                )
            answer = last_stdout.strip()
            if not answer:
                raise ValueError("Hermes answer assurance renderer returned empty output")
            return answer
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))

    raise RuntimeError(
        "Hermes answer assurance rendering failed after retries\n"
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


def render_assurance_fallback(
    *,
    query_text: str,
    packets: list[dict[str, Any]],
    quality_verdict: dict[str, Any],
) -> str:
    state = build_answer_state(packets=packets, query_text=query_text)
    summaries = state.get("packet_summaries", [])
    if not summaries:
        return (
            "I cannot support a stronger answer from the current context, so I can only answer conservatively. "
            "I would verify through Graphify first and then check linked SOT notes before making a stronger claim."
        )

    first = summaries[0]
    topic = first.get("topic") or "the current question"
    facts = [str(item).strip() for item in first.get("facts", []) if str(item).strip()]
    if facts:
        fact_text = " ".join(facts[:2])
        return (
            f"For your question about {topic}, the current grounded support indicates that {fact_text}. "
            "Anything beyond that would need direct verification against linked SOT notes."
        )

    return (
        f"For your question about {topic}, I only have partial grounded support right now. "
        "I would keep the answer conservative until I verify against linked SOT notes."
    )


def assure_answer_payload(
    *,
    query_text: str,
    packets: list[dict[str, Any]],
    answer_payload: dict[str, Any],
    quality_verdict: dict[str, Any],
) -> dict[str, Any]:
    gate_passed = bool(quality_verdict.get("quality_gate_passed"))
    if gate_passed:
        return {
            "applied": False,
            "assurance_mode": "pass_through",
            "reasons": [],
            "answer": answer_payload,
        }

    reasons = list(quality_verdict.get("quality_gate_reasons", []))
    state = build_answer_state(packets=packets, query_text=query_text)
    try:
        assured_text = render_assurance_via_hermes(
            query_text=query_text,
            state=state,
            initial_answer=str(answer_payload.get("answer_text") or ""),
            quality_verdict=quality_verdict,
        )
        assured_payload = {
            "rendering_mode": "hermes-assured-answer-edge",
            "answer_text": assured_text,
            "answer_hash": "sha256:" + hashlib.sha256(assured_text.encode("utf-8")).hexdigest(),
            "state": state,
        }
        return {
            "applied": True,
            "assurance_mode": "hermes-grounded-repair",
            "reasons": reasons,
            "answer": assured_payload,
        }
    except Exception as exc:
        fallback_text = render_assurance_fallback(
            query_text=query_text,
            packets=packets,
            quality_verdict=quality_verdict,
        )
        fallback_payload = {
            "rendering_mode": "deterministic-assurance-fallback",
            "answer_text": fallback_text,
            "answer_hash": "sha256:" + hashlib.sha256(fallback_text.encode("utf-8")).hexdigest(),
            "state": state,
            "render_error": str(exc),
        }
        return {
            "applied": True,
            "assurance_mode": "deterministic-grounded-fallback",
            "reasons": reasons,
            "answer": fallback_payload,
        }
