from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from harness_common import DEFAULT_VAULT, record_event, utc_now_iso
from common.map_identity import build_episode_id, build_page_id, build_topic_id, normalize_key
from evaluation.promotion_worthiness import (
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_HERMES_BIN,
    _run_wsl_python,
    build_session_context,
    load_session_json,
)
from placement.topic_episode_placement import validate_placement_verdict


def _session_episode_key(session: Mapping[str, Any], *, session_id: str) -> str:
    started = str(session.get("session_start") or "").strip()
    if started:
        if len(started) >= 10:
            return started[:10]
    if re.match(r"^\d{8}_\d{6}_", session_id):
        return f"{session_id[:4]}-{session_id[4:6]}-{session_id[6:8]}"
    return utc_now_iso()[:10]


def _title_from_topic_key(topic_key: str) -> str:
    return " ".join(part.capitalize() for part in normalize_key(topic_key).replace("/", " ").replace("_", " ").split("-"))


def list_existing_topics(*, vault_root: Path) -> list[dict[str, str]]:
    queries_root = vault_root / "queries"
    topics: list[dict[str, str]] = []
    if not queries_root.exists():
        return topics
    for path in sorted(queries_root.rglob("*.md")):
        rel = path.relative_to(vault_root).as_posix()
        title = path.stem.replace("-", " ").title()
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^title:\s*(.+)$", text, flags=re.MULTILINE)
        if match:
            title = match.group(1).strip().strip('"')
        topics.append(
            {
                "canonical_relative_path": rel,
                "topic_key": normalize_key(path.with_suffix("").relative_to(queries_root).as_posix()),
                "topic_title": title,
            }
        )
    return topics


def build_placement_prompt(*, context: Mapping[str, Any], existing_topics: list[dict[str, str]]) -> str:
    context_json = json.dumps(dict(context), ensure_ascii=False, indent=2)
    existing_json = json.dumps(existing_topics[:80], ensure_ascii=False, indent=2)
    return (
        "You are Hermes acting as the Map Maker for a map-first knowledge system.\n"
        "The user's latest question wording is not canonical identity.\n"
        "You must choose a stable topic key and topic title for long-term filing.\n"
        "If an existing topic is clearly the same durable subject, reuse its topic_key.\n"
        "If not, propose one stable new topic_key.\n"
        "Return ONLY one JSON object with this exact shape:\n"
        '{'
        '"topic_key":"stable-topic-key",'
        '"topic_title":"Human Title",'
        '"reason_labels":["same_topic_revisit"],'
        '"summary":"one sentence summary"'
        '}\n'
        "Rules:\n"
        "- topic_key must be short, durable, and not tied to a transient prompt wording.\n"
        "- topic_title must be human-readable.\n"
        "- reuse an existing topic_key when the durable topic is clearly the same.\n"
        "- prefer one stable topic over repeated duplicate topics across dates.\n\n"
        f"Existing canonical topics:\n{existing_json}\n\n"
        f"Session context:\n{context_json}\n"
    )


def render_placement_via_hermes(
    *,
    context: Mapping[str, Any],
    existing_topics: list[dict[str, str]],
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    if shutil.which("wsl") is None:
        raise RuntimeError("wsl command is not available")
    prompt = build_placement_prompt(context=context, existing_topics=existing_topics)
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
                    f"Hermes topic placement evaluation failed (returncode={completed.returncode})"
                )
            start = last_stdout.find("{")
            end = last_stdout.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON object found in Hermes placement output")
            payload = json.loads(last_stdout[start : end + 1])
            if not isinstance(payload, dict):
                raise ValueError("Hermes placement evaluator did not return an object")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))
    raise RuntimeError(
        "Hermes topic placement evaluation failed after retries\n"
        f"last_error={last_error!r}\n"
        f"stdout_preview={last_stdout[:800]!r}\n"
        f"stderr_preview={last_stderr[:800]!r}"
    )


def finalize_placement_verdict(
    *,
    profile: str,
    session_id: str,
    session_json_path: Path,
    raw_verdict: Mapping[str, Any],
    vault_root: Path = DEFAULT_VAULT,
) -> dict[str, Any]:
    session = load_session_json(session_json_path)
    topic_key = normalize_key(str(raw_verdict.get("topic_key") or ""))
    if not topic_key:
        raise RuntimeError("Map Maker did not return a valid topic_key")
    topic_id = build_topic_id(topic_key)
    episode_key = _session_episode_key(session, session_id=session_id)
    episode_id = build_episode_id(topic_id=topic_id, episode_key=episode_key)
    canonical_relative_path = f"queries/{topic_key}.md"
    page_id = build_page_id(canonical_relative_path)
    topic_title = str(raw_verdict.get("topic_title") or _title_from_topic_key(topic_key)).strip()
    page_path = vault_root / canonical_relative_path
    episode_marker = f"<!-- episode:{episode_id}:start -->"
    page_exists = page_path.exists()
    has_episode = page_exists and episode_marker in page_path.read_text(encoding="utf-8")
    if page_exists and has_episode:
        placement_mode = "existing_topic_existing_episode"
    elif page_exists:
        placement_mode = "existing_topic_new_episode"
    else:
        placement_mode = "new_topic_new_episode"
    page_action = "update_existing_page" if page_exists else "create_new_page"
    reasons = [str(item).strip() for item in raw_verdict.get("reason_labels", []) if str(item).strip()]
    if not reasons:
        reasons = [str(item).strip() for item in raw_verdict.get("reasons", []) if str(item).strip()]
    if not reasons:
        reasons = [placement_mode]
    verdict = {
        "schema_version": "topic_episode_placement.v1",
        "profile": profile,
        "session_id": session_id,
        "place": True,
        "topic_id": topic_id,
        "episode_id": episode_id,
        "page_id": page_id,
        "canonical_relative_path": canonical_relative_path,
        "topic_title": topic_title,
        "placement_mode": placement_mode,
        "page_action": page_action,
        "claim_actions": ["append_claim"] if not has_episode else ["refresh_episode_claims"],
        "reasons": reasons,
        "evaluation_mode": "hermes_runtime",
        "evaluated_at": utc_now_iso(),
    }
    validate_placement_verdict(verdict)
    return verdict


def evaluate_session_placement(
    *,
    session_json_path: Path,
    profile: str,
    session_id: str,
    vault_root: Path = DEFAULT_VAULT,
    evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    context = build_session_context(
        session_json_path=session_json_path,
        profile=profile,
        session_id=session_id,
    )
    existing_topics = list_existing_topics(vault_root=vault_root)
    active_evaluator = evaluator or render_placement_via_hermes
    raw_verdict = active_evaluator(context=context, existing_topics=existing_topics)
    verdict = finalize_placement_verdict(
        profile=profile,
        session_id=session_id,
        session_json_path=session_json_path,
        raw_verdict=raw_verdict,
        vault_root=vault_root,
    )
    record_event(
        "topic_episode_placement_evaluated",
        {
            "profile": profile,
            "session_id": session_id,
            "session_json": str(session_json_path),
            "topic_id": verdict["topic_id"],
            "episode_id": verdict["episode_id"],
            "canonical_relative_path": verdict["canonical_relative_path"],
            "placement_mode": verdict["placement_mode"],
            "page_action": verdict["page_action"],
        },
    )
    return verdict


def ensure_promotion_job_has_placement(job: Mapping[str, Any]) -> dict[str, Any]:
    from placement.topic_episode_placement import ensure_promotion_job_has_placement as ensure

    return ensure(job)
