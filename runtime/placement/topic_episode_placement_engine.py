from __future__ import annotations

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS
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
from admission.decision_contracts import validate_map_topography
from evaluation.promotion_worthiness import (
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_HERMES_BIN,
    _run_wsl_python,
    build_session_context,
    load_session_json,
)
from placement.topic_episode_placement import validate_placement_verdict
from placement.topic_index_catalog import (
    load_topic_index,
    upsert_topic_index_from_placement,
)


STRUCTURAL_PLACEMENT_SCHEMA_VERSION = "map_maker_structural_placement_result.v1"
STRUCTURAL_PLACEMENT_STATUS = "structural_placement_proven"
STRUCTURAL_EVIDENCE_MODE = "topic_episode_page_topography"


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


def _topic_key_from_topic_id(topic_id: str) -> str:
    if not topic_id.startswith("topic:"):
        raise ValueError("topic_id must start with topic:")
    return normalize_key(topic_id.split(":", 1)[1])


def _episode_parts(episode_id: str) -> tuple[str, str]:
    if not episode_id.startswith("episode:"):
        raise ValueError("episode_id must start with episode:")
    body = episode_id.split(":", 1)[1]
    if ":" not in body:
        raise ValueError("episode_id must include topic key and episode key")
    topic_key, episode_key = body.rsplit(":", 1)
    return normalize_key(topic_key), normalize_key(episode_key)


def _expected_topic_key_from_path(canonical_relative_path: str) -> str:
    path = canonical_relative_path.strip()
    if not path.startswith("queries/") or not path.endswith(".md"):
        raise ValueError("canonical_relative_path must be a query markdown path")
    return normalize_key(path[len("queries/") : -len(".md")])


def _safe_authority_boundary(map_topography: Mapping[str, Any] | None) -> dict[str, Any]:
    if map_topography is None:
        return {
            "map_maker_authority": "placement_only",
            "semantic_worth_authority": "not_map_maker",
            "category_authority": "not_map_maker",
            "bridge_topology_authority": "not_map_maker",
            "graphify_is_sot": False,
            "bridge_creation_allowed": False,
        }
    return {
        "map_maker_authority": str(map_topography.get("map_maker_authority") or ""),
        "semantic_worth_authority": str(map_topography.get("semantic_worth_authority") or ""),
        "category_authority": str(map_topography.get("category_authority") or ""),
        "bridge_topology_authority": str(map_topography.get("bridge_topology_authority") or ""),
        "graphify_is_sot": False,
        "bridge_creation_allowed": bool(map_topography.get("bridge_creation_allowed")),
    }


def _topography_alignment(
    *,
    placement_verdict: Mapping[str, Any],
    map_topography: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if map_topography is None:
        return {
            "map_topography_aligned": False,
            "topography_id": None,
            "continent_id": None,
            "continent_key": None,
            "bed_id": None,
            "placement_source": None,
            "category_source": None,
        }
    validate_map_topography(map_topography)
    comparisons = (
        ("topic_id", "topography_topic_id_mismatch"),
        ("page_id", "topography_page_id_mismatch"),
        ("canonical_relative_path", "topography_canonical_path_mismatch"),
    )
    for key, reason in comparisons:
        if str(map_topography.get(key) or "") != str(placement_verdict.get(key) or ""):
            raise ValueError(reason)
    return {
        "map_topography_aligned": True,
        "topography_id": str(map_topography.get("topography_id") or ""),
        "continent_id": str(map_topography.get("continent_id") or ""),
        "continent_key": str(map_topography.get("continent_key") or ""),
        "bed_id": str(map_topography.get("bed_id") or ""),
        "placement_source": str(map_topography.get("placement_source") or ""),
        "category_source": str(map_topography.get("category_source") or ""),
    }


def _structural_edges(*, topic_id: str, page_id: str, episode_id: str) -> list[dict[str, str]]:
    return [
        {
            "edge_type": "topic_owns_page",
            "from_id": topic_id,
            "to_id": page_id,
        },
        {
            "edge_type": "topic_contains_episode",
            "from_id": topic_id,
            "to_id": episode_id,
        },
        {
            "edge_type": "page_records_episode",
            "from_id": page_id,
            "to_id": episode_id,
        },
    ]


def build_map_maker_structural_placement_result(
    *,
    placement_verdict: Mapping[str, Any],
    map_topography: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    verdict = dict(placement_verdict)
    validate_placement_verdict(verdict)
    if verdict.get("place") is not True:
        raise ValueError("Structural placement requires place=true")

    topic_id = str(verdict["topic_id"])
    episode_id = str(verdict["episode_id"])
    page_id = str(verdict["page_id"])
    canonical_relative_path = str(verdict["canonical_relative_path"])
    topic_key = _topic_key_from_topic_id(topic_id)
    episode_topic_key, episode_key = _episode_parts(episode_id)
    path_topic_key = _expected_topic_key_from_path(canonical_relative_path)
    expected_page_id = build_page_id(canonical_relative_path)

    if episode_topic_key != topic_key:
        raise ValueError("episode_topic_id_mismatch")
    if path_topic_key != topic_key:
        raise ValueError("canonical_path_topic_mismatch")
    if page_id != expected_page_id:
        raise ValueError("page_id_canonical_path_mismatch")

    alignment = _topography_alignment(
        placement_verdict=verdict,
        map_topography=map_topography,
    )
    result = {
        "schema_version": STRUCTURAL_PLACEMENT_SCHEMA_VERSION,
        "status": STRUCTURAL_PLACEMENT_STATUS,
        "profile": str(verdict["profile"]),
        "session_id": str(verdict["session_id"]),
        "topic_id": topic_id,
        "topic_key": topic_key,
        "topic_title": str(verdict["topic_title"]),
        "episode_id": episode_id,
        "episode_key": episode_key,
        "page_id": page_id,
        "canonical_relative_path": canonical_relative_path,
        "placement_mode": str(verdict["placement_mode"]),
        "page_action": str(verdict["page_action"]),
        "structural_evidence_mode": STRUCTURAL_EVIDENCE_MODE,
        "structural_placement_used": True,
        "shallow_placement_only": False,
        "structural_edges": _structural_edges(
            topic_id=topic_id,
            page_id=page_id,
            episode_id=episode_id,
        ),
        "topography_alignment": alignment,
        "authority_boundary": _safe_authority_boundary(map_topography),
        "raw_provider_material_included": False,
        "local_filesystem_path_included": False,
        "generated_at": generated_at or utc_now_iso(),
    }
    validate_map_maker_structural_placement_result(result)
    return result


def validate_map_maker_structural_placement_result(result: Mapping[str, Any]) -> None:
    if result.get("schema_version") != STRUCTURAL_PLACEMENT_SCHEMA_VERSION:
        raise ValueError("Invalid Map Maker structural placement result schema_version")
    if result.get("status") != STRUCTURAL_PLACEMENT_STATUS:
        raise ValueError("Map Maker structural placement result is not proven")
    if result.get("structural_evidence_mode") != STRUCTURAL_EVIDENCE_MODE:
        raise ValueError("Map Maker structural placement requires topic/episode/page/topography evidence")
    if result.get("structural_placement_used") is not True:
        raise ValueError("Map Maker structural placement must use structural placement")
    if result.get("shallow_placement_only") is not False:
        raise ValueError("Map Maker structural placement must not be shallow-only")
    if result.get("raw_provider_material_included") is not False:
        raise ValueError("Map Maker structural placement must not include raw provider material")
    if result.get("local_filesystem_path_included") is not False:
        raise ValueError("Map Maker structural placement must not include local filesystem paths")

    topic_id = str(result.get("topic_id") or "")
    episode_id = str(result.get("episode_id") or "")
    page_id = str(result.get("page_id") or "")
    canonical_relative_path = str(result.get("canonical_relative_path") or "")
    topic_key = _topic_key_from_topic_id(topic_id)
    episode_topic_key, _ = _episode_parts(episode_id)
    if topic_key != episode_topic_key:
        raise ValueError("episode_topic_id_mismatch")
    if _expected_topic_key_from_path(canonical_relative_path) != topic_key:
        raise ValueError("canonical_path_topic_mismatch")
    if build_page_id(canonical_relative_path) != page_id:
        raise ValueError("page_id_canonical_path_mismatch")

    edges = result.get("structural_edges")
    expected_edges = _structural_edges(topic_id=topic_id, page_id=page_id, episode_id=episode_id)
    if edges != expected_edges:
        raise ValueError("Map Maker structural placement edges do not match identifiers")

    alignment = result.get("topography_alignment")
    if not isinstance(alignment, Mapping):
        raise ValueError("Map Maker structural placement requires topography_alignment")
    if alignment.get("map_topography_aligned") is not True:
        raise ValueError("Map Maker structural placement requires aligned map_topography")
    authority = result.get("authority_boundary")
    if not isinstance(authority, Mapping):
        raise ValueError("Map Maker structural placement requires authority_boundary")
    if authority.get("map_maker_authority") != "placement_only":
        raise ValueError("Map Maker authority must remain placement_only")
    if authority.get("semantic_worth_authority") != "not_map_maker":
        raise ValueError("Map Maker must not claim semantic worth authority")
    if authority.get("category_authority") != "not_map_maker":
        raise ValueError("Map Maker must not claim category authority")
    if authority.get("bridge_topology_authority") != "not_map_maker":
        raise ValueError("Map Maker must not claim bridge topology authority")
    if authority.get("bridge_creation_allowed") is not False:
        raise ValueError("Map Maker structural placement must not create bridges")
    if authority.get("graphify_is_sot") is not False:
        raise ValueError("Graphify must not be SOT for Map Maker structural placement")
    serialized = json.dumps(dict(result), ensure_ascii=False, sort_keys=True).replace("\\", "/").lower()
    if "d:/" in serialized or "c:/" in serialized or "file://" in serialized:
        raise ValueError("Map Maker structural placement result must not include local filesystem paths")


def list_existing_topics(*, vault_root: Path) -> list[dict[str, str]]:
    index_entries = load_topic_index(vault_root=vault_root)
    if index_entries:
        return [
            {
                "canonical_relative_path": str(entry["canonical_relative_path"]),
                "topic_key": str(entry["topic_key"]),
                "topic_title": str(entry["title"]),
            }
            for entry in index_entries
        ]

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
        except RECOVERABLE_RUNTIME_ERRORS as exc:
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
    topic_index_update = upsert_topic_index_from_placement(
        vault_root=vault_root,
        placement_verdict=verdict,
        one_line_summary=raw_verdict.get("summary"),
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
            "topic_index_status": topic_index_update["status"],
            "topic_index_ref": topic_index_update["index_ref"],
        },
    )
    return verdict


def ensure_promotion_job_has_placement(job: Mapping[str, Any]) -> dict[str, Any]:
    from placement.topic_episode_placement import ensure_promotion_job_has_placement as ensure

    return ensure(job)
