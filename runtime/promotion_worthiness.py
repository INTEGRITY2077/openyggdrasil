from __future__ import annotations

import base64
import json
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping

import jsonschema

from harness_common import (
    DEFAULT_HERMES_BIN,
    hermes_profile_home_win,
    record_event,
    utc_now_iso,
)


PROJECT_ROOT = Path(__file__).resolve().parent
PROMOTION_WORTHINESS_SCHEMA_PATH = PROJECT_ROOT.parent / "contracts" / "promotion_worthiness.v1.schema.json"
DEFAULT_MIN_ASSISTANT_CHARS = 80
DEFAULT_PROMOTION_SCORE_THRESHOLD = 0.68
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY_SECONDS = 1.0
HERMES_HOME_UNC = hermes_profile_home_win("default")
TOOL_LIMIT_MARKER = "you've reached the maximum number of tool-calling iterations allowed"
CLARIFY_TIMEOUT_MARKER = "the user did not provide a response within the time limit"
FAILURE_MARKERS = (
    "can't answer reliably",
    "could not answer reliably",
    "couldn't locate",
    "could not locate",
    "without the relevant repo",
    "without the relevant repo or documentation path",
    "did not get to read",
    "best-effort from the available context",
)
NEGATIVE_REASON_LABELS = {
    "trivial_lookup",
    "ephemeral_chat",
    "restatement_only",
    "minor_detail",
    "insufficient_decision_content",
}
POSITIVE_REASON_LABELS = {
    "durable_decision",
    "novel_synthesis",
    "substantial_comparison",
    "deep_dive",
    "hard_to_rederive",
}


@lru_cache(maxsize=1)
def load_worthiness_schema() -> Dict[str, Any]:
    return json.loads(PROMOTION_WORTHINESS_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_worthiness_verdict(verdict: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(verdict), schema=load_worthiness_schema())


def hermes_profile_home(profile: str) -> Path:
    if profile == "default":
        return HERMES_HOME_UNC
    return HERMES_HOME_UNC / "profiles" / profile


def resolve_session_json_path(
    *,
    profile: str | None,
    session_id: str | None,
    session_json: str | None,
) -> tuple[str, Path]:
    normalized_profile = profile or "default"
    if session_json:
        path = Path(session_json)
        if not path.exists():
            raise RuntimeError(f"Session JSON not found: {path}")
        return normalized_profile, path
    if not session_id:
        raise RuntimeError("session_id or session_json is required for worthiness evaluation")
    path = hermes_profile_home(normalized_profile) / "sessions" / f"session_{session_id}.json"
    if not path.exists():
        raise RuntimeError(f"Session JSON not found for id {session_id}: {path}")
    return normalized_profile, path


def load_session_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _message_text(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                chunks.append(str(item["text"]))
        return "\n".join(chunks).strip()
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def first_user_text(messages: List[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user":
            text = _message_text(message)
            if text:
                return text
    return ""


def last_nonempty_user_text(messages: List[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            text = _message_text(message)
            if text:
                return text
    return ""


def final_assistant_text(messages: List[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant":
            text = _message_text(message)
            if text:
                return text
    return ""


def quality_summary(path: Path, *, min_assistant_chars: int = DEFAULT_MIN_ASSISTANT_CHARS) -> dict[str, Any]:
    session = load_session_json(path)
    messages = session.get("messages", [])
    user_messages = [str(_message_text(msg) or "").strip() for msg in messages if msg.get("role") == "user"]
    assistant_messages = [str(_message_text(msg) or "").strip() for msg in messages if msg.get("role") == "assistant"]
    tool_messages = [str(_message_text(msg) or "").strip() for msg in messages if msg.get("role") == "tool"]
    assistant_entries = [msg for msg in messages if msg.get("role") == "assistant"]

    topic = user_messages[0] if user_messages else ""
    final_assistant = next((msg for msg in reversed(assistant_messages) if msg), "")
    topic_lower = topic.lower()
    final_lower = final_assistant.lower()
    reasons: list[str] = []

    if not topic:
        reasons.append("missing_user_prompt")
    if len(topic.split()) < 2:
        reasons.append("prompt_too_short")
    if topic_lower == "say" or topic_lower.startswith("say only ") or "wiki_ok" in topic_lower or "graph_ok" in topic_lower:
        reasons.append("test_prompt")
    if any(TOOL_LIMIT_MARKER in msg.lower() for msg in user_messages):
        reasons.append("tool_limit_reached")
    if any(
        call.get("function", {}).get("name") == "clarify"
        for msg in assistant_entries
        for call in msg.get("tool_calls", [])
    ):
        reasons.append("clarify_invoked")
    if any(CLARIFY_TIMEOUT_MARKER in msg.lower() for msg in tool_messages):
        reasons.append("clarify_timeout")
    if len(final_assistant) < min_assistant_chars:
        reasons.append("assistant_too_short")
    if any(marker in final_lower for marker in FAILURE_MARKERS):
        reasons.append("assistant_failure_style")

    return {
        "topic": topic,
        "assistant_chars": len(final_assistant),
        "assistant_preview": final_assistant[:160],
        "reasons": reasons,
        "ok": not reasons,
    }


def build_session_context(
    *,
    session_json_path: Path,
    profile: str,
    session_id: str,
) -> dict[str, Any]:
    session = load_session_json(session_json_path)
    messages = list(session.get("messages") or [])
    excerpts: list[dict[str, str]] = []
    for message in messages[-6:]:
        role = str(message.get("role") or "unknown")
        text = " ".join(_message_text(message).split())
        if not text:
            continue
        excerpts.append({"role": role, "text": text[:320]})
    return {
        "profile": profile,
        "session_id": session_id,
        "session_json_path": str(session_json_path),
        "message_count": len(messages),
        "first_user_message": first_user_text(messages),
        "last_user_message": last_nonempty_user_text(messages),
        "final_assistant_message": final_assistant_text(messages),
        "conversation_excerpt": excerpts,
    }


def build_worthiness_prompt(*, context: Mapping[str, Any], prefilter: Mapping[str, Any]) -> str:
    context_json = json.dumps(dict(context), ensure_ascii=False, indent=2)
    prefilter_json = json.dumps(dict(prefilter), ensure_ascii=False, indent=2)
    return (
        "You are Hermes evaluating whether a finished session should be promoted into the durable LLM Wiki SOT.\n"
        "Follow Andrej Karpathy's LLM Wiki filing discipline.\n"
        "Promote only if the session contains durable, non-trivial, hard-to-rederive knowledge, decision, comparison, or synthesis.\n"
        "Do not promote trivial lookups, ephemeral chat, passing mentions, or answers that mainly restate obvious facts.\n"
        "Return ONLY one JSON object with this exact shape:\n"
        '{'
        '"durability_score": 0.0,'
        '"novelty_score": 0.0,'
        '"decision_density_score": 0.0,'
        '"rederivation_cost_score": 0.0,'
        '"triviality_score": 0.0,'
        '"reason_labels": ["durable_decision"],'
        '"summary": "short summary"'
        '}\n'
        "Scoring rules:\n"
        "- durability_score: high only if the result is likely worth keeping for future sessions.\n"
        "- novelty_score: high only if the answer adds real synthesis rather than simple restatement.\n"
        "- decision_density_score: high only if the answer contains conclusions, tradeoffs, or structured judgment.\n"
        "- rederivation_cost_score: high only if reconstructing the result later would be meaningfully costly.\n"
        "- triviality_score: high only if the session is mostly a trivial lookup, ephemeral chat, or minor detail.\n"
        "Allowed reason_labels include: durable_decision, novel_synthesis, substantial_comparison, deep_dive, hard_to_rederive, trivial_lookup, ephemeral_chat, restatement_only, minor_detail, insufficient_decision_content.\n"
        "Use at most 4 reason_labels. Keep summary to one sentence.\n\n"
        f"Deterministic prefilter result:\n{prefilter_json}\n\n"
        f"Session context:\n{context_json}\n"
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


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in Hermes worthiness output")
    return json.loads(text[start : end + 1])


def render_worthiness_via_hermes(
    *,
    context: Mapping[str, Any],
    prefilter: Mapping[str, Any],
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    prompt = build_worthiness_prompt(context=context, prefilter=prefilter)
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
                    f"Hermes promotion worthiness evaluation failed (returncode={completed.returncode})"
                )
            payload = _extract_json_object(last_stdout)
            if not isinstance(payload, dict):
                raise ValueError("Hermes promotion worthiness evaluator did not return an object")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))
    raise RuntimeError(
        "Hermes promotion worthiness evaluation failed after retries\n"
        f"last_error={last_error!r}\n"
        f"stdout_preview={last_stdout[:800]!r}\n"
        f"stderr_preview={last_stderr[:800]!r}"
    )


def _normalized_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, score))


def _normalized_reason_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        label = str(item).strip()
        if label and label not in labels:
            labels.append(label)
    return labels[:4]


def finalize_worthiness_verdict(
    *,
    profile: str,
    session_id: str,
    prefilter: Mapping[str, Any],
    raw_verdict: Mapping[str, Any] | None = None,
    score_threshold: float = DEFAULT_PROMOTION_SCORE_THRESHOLD,
) -> dict[str, Any]:
    prefilter_ok = bool(prefilter.get("ok"))
    prefilter_reasons = [str(item) for item in prefilter.get("reasons", [])]
    if not prefilter_ok or raw_verdict is None:
        verdict = {
            "schema_version": "promotion_worthiness.v1",
            "profile": profile,
            "session_id": session_id,
            "promote": False,
            "score": 0.0,
            "durability_score": 0.0,
            "novelty_score": 0.0,
            "decision_density_score": 0.0,
            "rederivation_cost_score": 0.0,
            "triviality_score": 1.0 if prefilter_reasons else 0.0,
            "prefilter_ok": prefilter_ok,
            "prefilter_reasons": prefilter_reasons,
            "evaluation_mode": "prefilter_only",
            "reason_labels": ["prefilter_rejected"] if prefilter_reasons else [],
            "summary": "Session did not pass the deterministic prefilter for promotion." if prefilter_reasons else "No worthiness evaluation was run.",
            "evaluated_at": utc_now_iso(),
        }
        validate_worthiness_verdict(verdict)
        return verdict

    durability = _normalized_score(raw_verdict.get("durability_score"))
    novelty = _normalized_score(raw_verdict.get("novelty_score"))
    decision_density = _normalized_score(raw_verdict.get("decision_density_score"))
    rederivation_cost = _normalized_score(raw_verdict.get("rederivation_cost_score"))
    triviality = _normalized_score(raw_verdict.get("triviality_score"))
    reason_labels = _normalized_reason_labels(raw_verdict.get("reason_labels"))
    summary = str(raw_verdict.get("summary") or "").strip()
    if not summary:
        summary = "Hermes runtime did not provide a summary, so the worthiness gate is relying on the returned scores only."

    score = (
        durability * 0.28
        + novelty * 0.16
        + decision_density * 0.24
        + rederivation_cost * 0.20
        + (1.0 - triviality) * 0.12
    )
    has_positive_reason = any(label in POSITIVE_REASON_LABELS for label in reason_labels)
    has_negative_reason = any(label in NEGATIVE_REASON_LABELS for label in reason_labels)
    promote = bool(
        score >= score_threshold
        and durability >= 0.65
        and decision_density >= 0.60
        and rederivation_cost >= 0.55
        and triviality <= 0.40
        and has_positive_reason
        and not has_negative_reason
    )

    verdict = {
        "schema_version": "promotion_worthiness.v1",
        "profile": profile,
        "session_id": session_id,
        "promote": promote,
        "score": round(score, 4),
        "durability_score": durability,
        "novelty_score": novelty,
        "decision_density_score": decision_density,
        "rederivation_cost_score": rederivation_cost,
        "triviality_score": triviality,
        "prefilter_ok": prefilter_ok,
        "prefilter_reasons": prefilter_reasons,
        "evaluation_mode": "hermes_runtime",
        "reason_labels": reason_labels,
        "summary": summary,
        "evaluated_at": utc_now_iso(),
    }
    validate_worthiness_verdict(verdict)
    return verdict


def evaluate_session_worthiness(
    *,
    session_json_path: Path,
    profile: str,
    session_id: str,
    min_assistant_chars: int = DEFAULT_MIN_ASSISTANT_CHARS,
    evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    prefilter = quality_summary(session_json_path, min_assistant_chars=min_assistant_chars)
    if not prefilter["ok"]:
        verdict = finalize_worthiness_verdict(
            profile=profile,
            session_id=session_id,
            prefilter=prefilter,
            raw_verdict=None,
        )
    else:
        context = build_session_context(
            session_json_path=session_json_path,
            profile=profile,
            session_id=session_id,
        )
        active_evaluator = evaluator or render_worthiness_via_hermes
        raw_verdict = active_evaluator(context=context, prefilter=prefilter)
        verdict = finalize_worthiness_verdict(
            profile=profile,
            session_id=session_id,
            prefilter=prefilter,
            raw_verdict=raw_verdict,
        )
    record_event(
        "promotion_worthiness_evaluated",
        {
            "profile": profile,
            "session_id": session_id,
            "session_json": str(session_json_path),
            "promote": verdict["promote"],
            "score": verdict["score"],
            "evaluation_mode": verdict["evaluation_mode"],
            "reason_labels": verdict["reason_labels"],
            "prefilter_reasons": verdict["prefilter_reasons"],
        },
    )
    return verdict


def ensure_promotion_job_has_worthiness(job: Mapping[str, Any]) -> dict[str, Any]:
    payload = job.get("payload", {})
    verdict = payload.get("worthiness_verdict")
    if not isinstance(verdict, Mapping):
        raise RuntimeError("promotion job is missing worthiness_verdict")
    verdict_dict = dict(verdict)
    validate_worthiness_verdict(verdict_dict)
    if not verdict_dict.get("promote"):
        raise RuntimeError("promotion job worthiness_verdict does not allow promotion")
    payload_session = payload.get("session_id")
    verdict_session = verdict_dict.get("session_id")
    if payload_session and verdict_session and str(payload_session) != str(verdict_session):
        raise RuntimeError("promotion job worthiness_verdict session_id does not match payload.session_id")
    payload_profile = payload.get("profile") or "default"
    verdict_profile = verdict_dict.get("profile") or "default"
    if str(payload_profile) != str(verdict_profile):
        raise RuntimeError("promotion job worthiness_verdict profile does not match payload.profile")
    return verdict_dict
