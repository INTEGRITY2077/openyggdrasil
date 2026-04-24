from __future__ import annotations

import base64
import json
import re
import shutil
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema

from harness_common import DEFAULT_VAULT, utc_now_iso
from common.map_identity import build_claim_id, build_page_id, build_topic_id
from evaluation.promotion_worthiness import (
    DEFAULT_HERMES_BIN,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    _run_wsl_python,
)
from placement.topic_episode_placement_engine import list_existing_topics
from provenance.provenance_store import parse_provenance_records, provenance_page_path


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
PATHFINDER_SCHEMA_PATH = OPENYGGDRASIL_ROOT / "contracts" / "pathfinder.v1.schema.json"


@lru_cache(maxsize=1)
def load_pathfinder_schema() -> dict[str, Any]:
    return json.loads(PATHFINDER_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_pathfinder_bundle(bundle: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(bundle), schema=load_pathfinder_schema())


def _topic_page_title(text: str, fallback: str) -> str:
    match = re.search(r"^title:\s*(.+)$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"')
    return fallback


def parse_episode_blocks(text: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r"<!-- episode:(?P<episode_id>[^:]+:[^:]+:[^:]+):start -->\s*"
        r"(?P<body>.*?)"
        r"<!-- episode:(?P=episode_id):end -->",
        flags=re.DOTALL,
    )
    rows: list[dict[str, str]] = []
    for match in pattern.finditer(text):
        body = match.group("body").strip()
        summary = ""
        question_match = re.search(r"### Question\s*(?P<question>.*?)\s*### Answer", body, flags=re.DOTALL)
        answer_match = re.search(r"### Answer\s*(?P<answer>.*)$", body, flags=re.DOTALL)
        question = ""
        answer = ""
        if question_match:
            question = " ".join(question_match.group("question").split())[:240]
        if answer_match:
            answer = " ".join(answer_match.group("answer").split())[:240]
        if answer:
            summary = answer
        elif question:
            summary = question
        else:
            summary = body.replace("\n", " ").strip()[:240]
        rows.append(
            {
                "episode_id": match.group("episode_id"),
                "summary": summary,
                "question": question,
                "answer": answer,
            }
        )
    return rows


def build_anchor_prompt(*, query_text: str, existing_topics: list[dict[str, str]]) -> str:
    existing_json = json.dumps(existing_topics[:80], ensure_ascii=False, indent=2)
    return (
        "You are Hermes acting as Pathfinder for a map-first memory system.\n"
        "Choose a stable existing topic anchor if the new question clearly revisits an existing durable topic.\n"
        "If the question does not clearly match an existing durable topic, return null anchor.\n"
        "Return ONLY one JSON object with this exact shape:\n"
        '{"topic_key":"stable-topic-key-or-null","reason_labels":["same_topic_revisit"],"summary":"one sentence"}\n'
        "Rules:\n"
        "- Reuse an existing topic only when the durable subject is clearly the same.\n"
        "- Do not anchor to a topic just because one or two words overlap.\n"
        "- If uncertain, return null for topic_key.\n\n"
        f"Existing canonical topics:\n{existing_json}\n\n"
        f"Query:\n{query_text}\n"
    )


def render_pathfinder_anchor_via_hermes(
    *,
    query_text: str,
    existing_topics: list[dict[str, str]],
    hermes_bin: str = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    if shutil.which("wsl") is None:
        raise RuntimeError("wsl command is not available")
    prompt = build_anchor_prompt(query_text=query_text, existing_topics=existing_topics)
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
                    f"Hermes Pathfinder anchor evaluation failed (returncode={completed.returncode})"
                )
            start = last_stdout.find("{")
            end = last_stdout.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON object found in Hermes Pathfinder output")
            payload = json.loads(last_stdout[start : end + 1])
            if not isinstance(payload, dict):
                raise ValueError("Hermes Pathfinder evaluator did not return an object")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))
    raise RuntimeError(
        "Hermes Pathfinder evaluation failed after retries\n"
        f"last_error={last_error!r}\n"
        f"stdout_preview={last_stdout[:800]!r}\n"
        f"stderr_preview={last_stderr[:800]!r}"
    )


def _unanchored_bundle(*, query_text: str) -> dict[str, Any]:
    bundle = {
        "schema_version": "pathfinder.v1",
        "query_text": query_text,
        "anchor_type": "none",
        "anchor_id": None,
        "topic_id": None,
        "anchor_title": None,
        "episode_ids": [],
        "claim_ids": [],
        "page_ids": [],
        "source_paths": [],
        "support_facts": [],
        "bundle_mode": "unanchored",
        "generated_at": utc_now_iso(),
    }
    validate_pathfinder_bundle(bundle)
    return bundle


def finalize_pathfinder_bundle(
    *,
    query_text: str,
    raw_anchor: Mapping[str, Any],
    vault_root: Path = DEFAULT_VAULT,
    episode_limit: int = 3,
) -> dict[str, Any]:
    topic_key = str(raw_anchor.get("topic_key") or "").strip()
    if not topic_key or topic_key.lower() == "null":
        return _unanchored_bundle(query_text=query_text)

    canonical_relative_path = f"queries/{topic_key}.md"
    page_path = vault_root / canonical_relative_path
    if not page_path.exists():
        return _unanchored_bundle(query_text=query_text)

    text = page_path.read_text(encoding="utf-8")
    topic_id = build_topic_id(topic_key)
    page_id = build_page_id(canonical_relative_path)
    anchor_title = _topic_page_title(text, fallback=page_path.stem.replace("-", " ").title())
    provenance_path = provenance_page_path(vault_root=vault_root, topic_id=topic_id)

    if provenance_path.exists():
        provenance_text = provenance_path.read_text(encoding="utf-8")
        provenance_rows = sorted(
            parse_provenance_records(provenance_text),
            key=lambda row: row["episode_id"],
            reverse=True,
        )
        selected_rows = provenance_rows[:episode_limit]
        selected_claim_ids = {str(row["claim_id"]) for row in selected_rows}
        related_claim_ids = {
            str(claim_id)
            for row in selected_rows
            for field in ("supports", "supersedes", "contradicts")
            for claim_id in row.get(field, [])
            if str(claim_id)
        }
        related_rows = [
            row
            for row in provenance_rows
            if str(row["claim_id"]) in related_claim_ids and str(row["claim_id"]) not in selected_claim_ids
        ]
        bundle_rows = selected_rows + related_rows
        episode_ids = [str(row["episode_id"]) for row in bundle_rows]
        claim_ids = [str(row["claim_id"]) for row in bundle_rows]
        source_paths = sorted(
            {
                str(page_path.resolve()),
                str(provenance_path.resolve()),
                *[str((vault_root / row["promoted_from"]).resolve()) for row in bundle_rows if row.get("promoted_from")],
            }
        )
        support_facts = [
            str(row.get("answer_summary") or row.get("question_summary") or "").strip()
            for row in bundle_rows
            if str(row.get("answer_summary") or row.get("question_summary") or "").strip()
        ]
        has_semantic_edges = any(
            row.get("supports") or row.get("supersedes") or row.get("contradicts")
            for row in selected_rows
        )
        bundle_mode = (
            "topic-page-latest-episodes-with-semantic-edges"
            if related_rows or has_semantic_edges
            else "topic-page-latest-episodes"
        )
    else:
        episodes = sorted(
            parse_episode_blocks(text),
            key=lambda row: row["episode_id"],
            reverse=True,
        )[:episode_limit]
        episode_ids = [row["episode_id"] for row in episodes]
        claim_ids = [
            build_claim_id(topic_id=topic_id, claim_key=f"{row['episode_id']}:summary")
            for row in episodes
        ]
        support_facts = [row["summary"] for row in episodes if row["summary"]]
        source_paths = [str(page_path.resolve())]
        bundle_mode = "topic-page-latest-episodes"

    bundle = {
        "schema_version": "pathfinder.v1",
        "query_text": query_text,
        "anchor_type": "topic",
        "anchor_id": topic_id,
        "topic_id": topic_id,
        "anchor_title": anchor_title,
        "episode_ids": episode_ids,
        "claim_ids": claim_ids,
        "page_ids": [page_id],
        "source_paths": source_paths,
        "support_facts": support_facts,
        "bundle_mode": bundle_mode,
        "generated_at": utc_now_iso(),
    }
    validate_pathfinder_bundle(bundle)
    return bundle


def build_pathfinder_bundle(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    existing_topics = list_existing_topics(vault_root=vault_root)
    active_evaluator = evaluator or render_pathfinder_anchor_via_hermes
    raw_anchor = active_evaluator(query_text=query_text, existing_topics=existing_topics)
    return finalize_pathfinder_bundle(
        query_text=query_text,
        raw_anchor=raw_anchor,
        vault_root=vault_root,
    )


def build_pathfinder_bundle_ptc_mvp(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    anchor_evaluator: Callable[..., Mapping[str, Any]] | None = None,
    program_source: str | None = None,
    recent_limit: int = 3,
) -> dict[str, Any]:
    from retrieval.pathfinder_ptc_mvp import build_pathfinder_bundle_via_ptc_mvp

    return build_pathfinder_bundle_via_ptc_mvp(
        query_text=query_text,
        vault_root=vault_root,
        anchor_evaluator=anchor_evaluator,
        program_source=program_source,
        recent_limit=recent_limit,
    )
