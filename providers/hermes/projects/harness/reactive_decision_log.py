from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from harness_common import DEFAULT_HERMES_BIN
from harness_i18n import normalize_requested_locale


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY_SECONDS = 1.0
MAX_QUERY_CHARS = 96
JSON_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def query_reminder(query_text: str) -> str:
    compact = " ".join(query_text.strip().split())
    if len(compact) <= MAX_QUERY_CHARS:
        return compact
    return compact[: MAX_QUERY_CHARS - 3].rstrip() + "..."


def build_decision_log_state(*, packets: list[dict], query_text: str) -> dict[str, Any]:
    graph_hints = sum(1 for packet in packets if packet.get("message_type") == "graph_hint")
    lint_alerts = sum(1 for packet in packets if packet.get("message_type") == "lint_alert")
    signal_labels: list[str] = []
    if graph_hints:
        signal_labels.append(f"Graphify hint x{graph_hints}")
    if lint_alerts:
        signal_labels.append(f"lint alert x{lint_alerts}")

    primary_action = "graphify_query_surface"
    if not packets:
        primary_action = "graphify_query_surface_without_packet_hint"

    cautions: list[str] = []
    if lint_alerts:
        cautions.append("warned_links_not_asserted")

    fallback_order = [
        "linked_sot_notes",
        "sot_raw_files",
    ]
    if not packets:
        fallback_order = [
            "graphify_query_surface",
            "linked_sot_notes",
            "sot_raw_files",
        ]

    return {
        "question_context": query_reminder(query_text),
        "received_signals": {
            "total_packets": len(packets),
            "graph_hints": graph_hints,
            "lint_alerts": lint_alerts,
            "labels": signal_labels,
        },
        "decision": {
            "primary_action": primary_action,
            "cautions": cautions,
        },
        "fallback": {
            "order": fallback_order,
        },
        "grounding": {
            "source_paths": _collect_source_paths(packets),
            "topic_candidates": _collect_topics(packets),
        },
    }


def _collect_source_paths(packets: list[dict]) -> list[str]:
    source_paths: list[str] = []
    for packet in packets:
        payload = packet.get("payload", {})
        for path in payload.get("source_paths", []):
            path_text = str(path)
            if path_text not in source_paths:
                source_paths.append(path_text)
    return source_paths[:5]


def _collect_topics(packets: list[dict]) -> list[str]:
    topics: list[str] = []
    for packet in packets:
        topic = packet.get("scope", {}).get("topic")
        if topic:
            topic_text = str(topic)
            if topic_text not in topics:
                topics.append(topic_text)
    return topics[:5]


def build_reactive_prompt(*, query_text: str, state: dict[str, Any], requested_locale: str | None) -> str:
    locale_clause = (
        f"Preferred locale override: {requested_locale}.\n"
        if requested_locale
        else "Preferred locale override: none. Follow the user's question language directly.\n"
    )
    state_json = json.dumps(state, ensure_ascii=False, indent=2)
    return (
        "You are rendering a short Hermes decision log that appears right before the final answer.\n"
        "Write in the same language as the user's question. If a preferred locale override is provided, honor it when natural.\n"
        "Do not translate the product tokens Graphify, SOT, RAW, or wiki.\n"
        "Return ONLY one valid JSON object with this exact shape:\n"
        '{"brief_lines":["line1","line2","line3","line4"]}\n'
        "Rules:\n"
        "- Exactly 4 lines.\n"
        "- No markdown, bullets, brackets, numbering, or labels.\n"
        "- Keep the lines direct, human, and question-centered.\n"
        "- Line 1 must remind the user of their question context.\n"
        "- Line 2 must say what subagent signal(s) just arrived and what state was confirmed.\n"
        "- Line 3 must say what Hermes will do first to narrow the answer.\n"
        "- Line 4 must say what Hermes will do next only if the current context is insufficient.\n"
        "- Avoid generic meta commentary.\n"
        "- Keep each line concise.\n\n"
        f"{locale_clause}"
        f"User question:\n{query_text}\n\n"
        f"Structured decision state:\n{state_json}\n"
    )


def render_brief_lines_via_hermes(
    *,
    query_text: str,
    state: dict[str, Any],
    requested_locale: str | None,
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> list[str]:
    prompt = build_reactive_prompt(
        query_text=query_text,
        state=state,
        requested_locale=normalize_requested_locale(requested_locale),
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
                    "Hermes reactive decision-log rendering failed "
                    f"(returncode={completed.returncode})"
                )
            normalized_lines = extract_brief_lines(last_stdout)
            if any(not line for line in normalized_lines):
                raise ValueError("Hermes renderer returned an empty brief line")
            return normalized_lines
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))

    raise RuntimeError(
        "Hermes reactive decision-log rendering failed after retries\n"
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


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in Hermes renderer output")
    return json.loads(text[start : end + 1])


def extract_brief_lines(text: str) -> list[str]:
    try:
        payload = extract_json_object(text)
        brief_lines = payload.get("brief_lines")
        if isinstance(brief_lines, list) and len(brief_lines) == 4:
            return [str(line).strip() for line in brief_lines]
    except Exception:
        pass

    marker = '"brief_lines"'
    start = text.find(marker)
    if start == -1:
        raise ValueError("brief_lines marker not found in Hermes renderer output")
    array_start = text.find("[", start)
    if array_start == -1:
        raise ValueError("brief_lines array start not found in Hermes renderer output")

    tail = text[array_start:]
    values = [json.loads(f'"{match}"') for match in JSON_STRING_RE.findall(tail)]
    if len(values) < 4:
        raise ValueError("Could not recover four brief lines from malformed Hermes renderer output")
    return [str(line).strip() for line in values[:4]]


def render_fallback_lines(*, query_text: str, state: dict[str, Any]) -> list[str]:
    signal_labels = state["received_signals"]["labels"]
    received = ", ".join(signal_labels) if signal_labels else "no directly relevant subagent signal"
    if state["decision"]["primary_action"] == "graphify_query_surface_without_packet_hint":
        first_step = "I will start with the Graphify query surface to narrow the answer."
    elif state["decision"]["cautions"]:
        first_step = "I will narrow the answer through Graphify-linked wiki context and stay conservative around warned links."
    else:
        first_step = "I will narrow the answer through the Graphify-linked wiki path first."

    return [
        f'Your question context was "{state["question_context"]}".',
        f"I just received {received} and confirmed the related state.",
        first_step,
        "If that is still not enough, I will go down to linked SOT notes and then SOT RAW files for direct verification.",
    ]


def render_decision_log_payload(
    *,
    packets: list[dict],
    query_text: str,
    requested_locale: str | None = None,
    renderer: Callable[..., list[str]] | None = None,
) -> dict[str, Any]:
    state = build_decision_log_state(packets=packets, query_text=query_text)
    active_renderer = renderer or render_brief_lines_via_hermes
    normalized_locale = normalize_requested_locale(requested_locale)
    try:
        brief_lines = active_renderer(
            query_text=query_text,
            state=state,
            requested_locale=normalized_locale,
        )
        rendering_mode = "hermes-reactive"
        render_error = None
    except Exception as exc:
        brief_lines = render_fallback_lines(query_text=query_text, state=state)
        rendering_mode = "deterministic-fallback"
        render_error = str(exc)

    payload: dict[str, Any] = {
        "rendering_mode": rendering_mode,
        "requested_locale": normalized_locale,
        "brief_lines": brief_lines,
        "state": state,
    }
    if render_error:
        payload["render_error"] = render_error
    return payload
