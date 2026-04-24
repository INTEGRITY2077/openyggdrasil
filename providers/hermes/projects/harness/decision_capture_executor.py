from __future__ import annotations

import base64
import json
import re
import time
import uuid
from typing import Any, Callable, Dict, Mapping

from decision_contracts import validate_decision_candidate, validate_decision_surface
from packet_factory import build_decision_candidate_packet
from plugin_logger import record_plugin_event
from postman_gateway import submit_packet
from promotion_worthiness import (
    DEFAULT_HERMES_BIN,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    _run_wsl_python,
)
from provider_attachment import build_session_uid
from harness_common import utc_now_iso


def build_decision_capture_prompt(*, decision_surface: Mapping[str, Any]) -> str:
    surface_json = json.dumps(dict(decision_surface), ensure_ascii=False, indent=2)
    return (
        "You are Hermes running as a provider-owned headless decision distiller.\n"
        "A foreground provider session identified a bounded decision surface.\n"
        "Extract only the durable decision candidate from that surface.\n"
        "Return ONLY one JSON object with this exact shape:\n"
        "{"
        '"decision_text":"one concise decision statement",'
        '"rationale":"short rationale",'
        '"alternatives_rejected":["rejected option"],'
        '"stability_state":"provisional",'
        '"topic_hint":"stable-topic-hint",'
        '"reason_labels":["durable_decision"],'
        '"confidence_score":0.0'
        "}\n"
        "Rules:\n"
        "- decision_text must be concrete and durable.\n"
        "- rationale must explain why the decision was made.\n"
        "- alternatives_rejected may be empty but must be present.\n"
        "- stability_state must be one of provisional, stable, superseding.\n"
        "- topic_hint should be short and durable.\n"
        "- confidence_score must be between 0.0 and 1.0.\n"
        "- If the surface is weak, still return a conservative provisional decision candidate.\n\n"
        f"Decision surface:\n{surface_json}\n"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in decision capture output")
    return json.loads(text[start : end + 1])


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
            payload = _extract_json_object(last_stdout)
            if not isinstance(payload, dict):
                raise ValueError("Hermes decision capture did not return an object")
            return payload
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


def _normalize_reason_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        label = str(item).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def _normalize_rejected_alternatives(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    alternatives: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            alternatives.append(text)
    return alternatives


def _normalize_confidence_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, score))


def _normalize_topic_hint(raw_value: Any, *, decision_surface: Mapping[str, Any]) -> str | None:
    text = str(raw_value or "").strip()
    if text:
        return text
    fallback = str(decision_surface.get("topic_hint") or "").strip()
    return fallback or None


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip().lower()).strip("-")
    return normalized or "decision"


def finalize_decision_candidate(
    *,
    profile: str,
    session_id: str,
    decision_surface: Mapping[str, Any],
    raw_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    session_uid = build_session_uid(
        provider_id="hermes",
        provider_profile=profile,
        provider_session_id=session_id,
    )
    turn_start = int(decision_surface["turn_start"])
    turn_end = int(decision_surface["turn_end"])
    topic_hint = _normalize_topic_hint(raw_candidate.get("topic_hint"), decision_surface=decision_surface)
    dedup_basis = topic_hint or str(decision_surface.get("surface_summary") or "")
    dedup_key = f"{session_uid}:{turn_start}-{turn_end}:{_slugify(dedup_basis)}"
    candidate = {
        "schema_version": "decision_candidate.v1",
        "candidate_id": uuid.uuid4().hex,
        "dedup_key": dedup_key,
        "provider_id": "hermes",
        "provider_profile": profile,
        "provider_session_id": session_id,
        "session_uid": session_uid,
        "turn_start": turn_start,
        "turn_end": turn_end,
        "surface_summary": str(decision_surface["surface_summary"]).strip(),
        "trigger_reason": str(decision_surface["trigger_reason"]).strip(),
        "decision_text": str(raw_candidate.get("decision_text") or "").strip(),
        "rationale": str(raw_candidate.get("rationale") or "").strip(),
        "alternatives_rejected": _normalize_rejected_alternatives(raw_candidate.get("alternatives_rejected")),
        "stability_state": str(raw_candidate.get("stability_state") or "provisional").strip() or "provisional",
        "topic_hint": topic_hint,
        "reason_labels": _normalize_reason_labels(raw_candidate.get("reason_labels")),
        "confidence_score": _normalize_confidence_score(raw_candidate.get("confidence_score")),
        "source_ref": decision_surface.get("source_ref"),
        "origin_locator": dict(decision_surface.get("origin_locator") or {}),
        "generated_at": utc_now_iso(),
    }
    validate_decision_candidate(candidate)
    return candidate


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
    validate_decision_surface(decision_surface)
    raw_candidate = (renderer or render_decision_candidate_via_hermes)(
        decision_surface=decision_surface,
    )
    decision_candidate = finalize_decision_candidate(
        profile=profile,
        session_id=session_id,
        decision_surface=decision_surface,
        raw_candidate=raw_candidate,
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
        },
        state={
            "stability_state": decision_candidate["stability_state"],
            "confidence_score": decision_candidate["confidence_score"],
            "reason_labels": decision_candidate["reason_labels"],
            "topic_hint": decision_candidate["topic_hint"],
        },
    )
    return {"packet": packet, "decision_candidate": decision_candidate}
