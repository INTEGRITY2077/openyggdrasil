from __future__ import annotations

import base64
import json
import shutil
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import jsonschema

from harness_common import record_event, utc_now_iso
from promotion_worthiness import (
    DEFAULT_HERMES_BIN,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    _run_wsl_python,
)


PROJECT_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = PROJECT_ROOT.parent / "contracts" / "episode_semantic_edges.v1.schema.json"


@lru_cache(maxsize=1)
def load_semantic_edge_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_semantic_edge_verdict(verdict: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(verdict), schema=load_semantic_edge_schema())


def build_semantic_edge_prompt(
    *,
    topic_id: str,
    current_question: str,
    current_answer: str,
    previous_candidates: Sequence[Mapping[str, Any]],
) -> str:
    candidates = [
        {
            "claim_id": str(row.get("claim_id") or ""),
            "episode_id": str(row.get("episode_id") or ""),
            "question_summary": str(row.get("question_summary") or ""),
            "answer_summary": str(row.get("answer_summary") or ""),
        }
        for row in previous_candidates
    ]
    candidates_json = json.dumps(candidates[:8], ensure_ascii=False, indent=2)
    return (
        "You are Hermes evaluating semantic edges between a current topic episode and previous episodes.\n"
        "Return ONLY one JSON object with this exact shape:\n"
        '{'
        '"supports":["claim:..."],'
        '"supersedes":["claim:..."],'
        '"contradicts":["claim:..."],'
        '"reason_labels":["supports_prior_claim"],'
        '"summary":"one sentence"'
        '}\n'
        "Rules:\n"
        "- Only use claim_id values from the provided candidate list.\n"
        "- supports: the new episode reinforces or extends a prior claim.\n"
        "- supersedes: the new episode replaces the operational conclusion of a prior claim.\n"
        "- contradicts: the new episode materially conflicts with a prior claim.\n"
        "- If no relation is clear, return empty arrays.\n"
        "- Do not invent claim ids.\n\n"
        f"Topic: {topic_id}\n\n"
        f"Current question:\n{current_question}\n\n"
        f"Current answer:\n{current_answer}\n\n"
        f"Previous candidate claims:\n{candidates_json}\n"
    )


def render_semantic_edges_via_hermes(
    *,
    topic_id: str,
    current_question: str,
    current_answer: str,
    previous_candidates: Sequence[Mapping[str, Any]],
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    if shutil.which("wsl") is None:
        raise RuntimeError("wsl command is not available")
    prompt = build_semantic_edge_prompt(
        topic_id=topic_id,
        current_question=current_question,
        current_answer=current_answer,
        previous_candidates=previous_candidates,
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
                    f"Hermes semantic edge evaluation failed (returncode={completed.returncode})"
                )
            start = last_stdout.find("{")
            end = last_stdout.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON object found in Hermes semantic edge output")
            payload = json.loads(last_stdout[start : end + 1])
            if not isinstance(payload, dict):
                raise ValueError("Hermes semantic edge evaluator did not return an object")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))
    raise RuntimeError(
        "Hermes semantic edge evaluation failed after retries\n"
        f"last_error={last_error!r}\n"
        f"stdout_preview={last_stdout[:800]!r}\n"
        f"stderr_preview={last_stderr[:800]!r}"
    )


def _normalize_claim_list(value: Any, *, allowed: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        claim_id = str(item).strip()
        if claim_id and claim_id in allowed and claim_id not in rows:
            rows.append(claim_id)
    return rows


def finalize_semantic_edge_verdict(
    *,
    raw_verdict: Mapping[str, Any] | None,
    previous_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    allowed_claim_ids = {str(row.get("claim_id") or "").strip() for row in previous_candidates}
    allowed_claim_ids.discard("")
    if not previous_candidates or raw_verdict is None:
        verdict = {
            "schema_version": "episode_semantic_edges.v1",
            "supports": [],
            "supersedes": [],
            "contradicts": [],
            "reason_labels": ["no_prior_episode_candidates"] if not previous_candidates else [],
            "summary": "No prior topic episodes were available for semantic edge evaluation."
            if not previous_candidates
            else "No semantic edge evaluation was run.",
            "evaluation_mode": "no_candidates" if not previous_candidates else "skipped",
            "evaluated_at": utc_now_iso(),
        }
        validate_semantic_edge_verdict(verdict)
        return verdict

    verdict = {
        "schema_version": "episode_semantic_edges.v1",
        "supports": _normalize_claim_list(raw_verdict.get("supports"), allowed=allowed_claim_ids),
        "supersedes": _normalize_claim_list(raw_verdict.get("supersedes"), allowed=allowed_claim_ids),
        "contradicts": _normalize_claim_list(raw_verdict.get("contradicts"), allowed=allowed_claim_ids),
        "reason_labels": [str(item).strip() for item in raw_verdict.get("reason_labels", []) if str(item).strip()][:4],
        "summary": str(raw_verdict.get("summary") or "").strip() or "Semantic edge evaluation completed.",
        "evaluation_mode": "hermes_runtime",
        "evaluated_at": utc_now_iso(),
    }
    validate_semantic_edge_verdict(verdict)
    return verdict


def evaluate_episode_semantic_edges(
    *,
    topic_id: str,
    current_question: str,
    current_answer: str,
    previous_candidates: Sequence[Mapping[str, Any]],
    evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not previous_candidates:
        verdict = finalize_semantic_edge_verdict(raw_verdict=None, previous_candidates=previous_candidates)
    else:
        active_evaluator = evaluator or render_semantic_edges_via_hermes
        raw_verdict = active_evaluator(
            topic_id=topic_id,
            current_question=current_question,
            current_answer=current_answer,
            previous_candidates=previous_candidates,
        )
        verdict = finalize_semantic_edge_verdict(
            raw_verdict=raw_verdict,
            previous_candidates=previous_candidates,
        )
    record_event(
        "episode_semantic_edges_evaluated",
        {
            "topic_id": topic_id,
            "candidate_count": len(previous_candidates),
            "supports": verdict["supports"],
            "supersedes": verdict["supersedes"],
            "contradicts": verdict["contradicts"],
            "evaluation_mode": verdict["evaluation_mode"],
        },
    )
    return verdict
