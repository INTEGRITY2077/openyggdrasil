from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from harness_common import DEFAULT_GRAPHIFY_SANDBOX, DEFAULT_VAULT, OPS_ROOT, utc_now_iso


GRAPHIFY_ROOT = OPS_ROOT / "graphify"
GRAPH_FRESHNESS_PATH = GRAPHIFY_ROOT / "graph-freshness.json"
DEFAULT_GRAPH_SUMMARY_PATH = Path(
    os.getenv(
        "GRAPHIFY_SUMMARY_PATH",
        str(DEFAULT_GRAPHIFY_SANDBOX / "graphify-out" / "summary.json"),
    )
)


def ensure_graphify_runtime_dirs() -> None:
    GRAPHIFY_ROOT.mkdir(parents=True, exist_ok=True)


def read_graph_freshness(path: Path = GRAPH_FRESHNESS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_graph_freshness(payload: dict[str, Any], path: Path = GRAPH_FRESHNESS_PATH) -> dict[str, Any]:
    ensure_graphify_runtime_dirs()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def latest_vault_markdown(vault_root: Path = DEFAULT_VAULT) -> tuple[float | None, str | None]:
    latest_mtime: float | None = None
    latest_path: str | None = None
    if not vault_root.exists():
        return None, None
    for path in vault_root.rglob("*.md"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if latest_mtime is None or mtime > latest_mtime:
            latest_mtime = mtime
            latest_path = str(path.resolve())
    return latest_mtime, latest_path


def graph_summary_mtime(summary_path: Path = DEFAULT_GRAPH_SUMMARY_PATH) -> float | None:
    if not summary_path.exists():
        return None
    return summary_path.stat().st_mtime


def current_graph_freshness(
    *,
    vault_root: Path = DEFAULT_VAULT,
    summary_path: Path = DEFAULT_GRAPH_SUMMARY_PATH,
    state_path: Path = GRAPH_FRESHNESS_PATH,
) -> dict[str, Any]:
    state = read_graph_freshness(state_path)
    latest_vault_mtime, latest_vault_path = latest_vault_markdown(vault_root)
    summary_mtime = graph_summary_mtime(summary_path)
    reasons: list[str] = []

    if summary_mtime is None:
        status = "missing"
        reasons.append("graph_summary_missing")
    elif latest_vault_mtime is not None and latest_vault_mtime > summary_mtime:
        status = "stale"
        reasons.append("vault_newer_than_graph_summary")
    else:
        status = "fresh"

    last_sot_write_at = state.get("last_sot_write_at")
    last_graph_rebuild_at = state.get("last_graph_rebuild_at")
    if last_sot_write_at and (not last_graph_rebuild_at or last_sot_write_at > last_graph_rebuild_at):
        status = "stale"
        if "sot_write_newer_than_graph_rebuild" not in reasons:
            reasons.append("sot_write_newer_than_graph_rebuild")

    return {
        "status": status,
        "graph_is_trusted": status == "fresh",
        "reasons": reasons,
        "vault_root": str(vault_root.resolve()) if vault_root.exists() else str(vault_root),
        "latest_vault_mtime": latest_vault_mtime,
        "latest_vault_path": latest_vault_path,
        "graph_summary_path": str(summary_path.resolve()),
        "graph_summary_mtime": summary_mtime,
        "last_sot_write_at": last_sot_write_at,
        "last_sot_write_job_id": state.get("last_sot_write_job_id"),
        "last_sot_write_parent_question_id": state.get("last_sot_write_parent_question_id"),
        "last_graph_rebuild_at": last_graph_rebuild_at,
        "last_graph_job_id": state.get("last_graph_job_id"),
        "last_graph_parent_question_id": state.get("last_graph_parent_question_id"),
    }


def mark_sot_write(
    *,
    job_id: str | None,
    parent_question_id: str | None,
    vault_root: Path = DEFAULT_VAULT,
    summary_path: Path = DEFAULT_GRAPH_SUMMARY_PATH,
    state_path: Path = GRAPH_FRESHNESS_PATH,
) -> dict[str, Any]:
    state = read_graph_freshness(state_path)
    latest_mtime, latest_path = latest_vault_markdown(vault_root)
    state.update(
        {
            "updated_at": utc_now_iso(),
            "last_sot_write_at": utc_now_iso(),
            "last_sot_write_job_id": job_id,
            "last_sot_write_parent_question_id": parent_question_id,
            "latest_vault_mtime": latest_mtime,
            "latest_vault_path": latest_path,
            "graph_summary_path": str(summary_path.resolve()),
        }
    )
    write_graph_freshness(state, state_path)
    return current_graph_freshness(vault_root=vault_root, summary_path=summary_path, state_path=state_path)


def mark_graph_rebuild(
    *,
    job_id: str | None,
    parent_question_id: str | None,
    vault_root: Path = DEFAULT_VAULT,
    summary_path: Path = DEFAULT_GRAPH_SUMMARY_PATH,
    state_path: Path = GRAPH_FRESHNESS_PATH,
) -> dict[str, Any]:
    state = read_graph_freshness(state_path)
    latest_mtime, latest_path = latest_vault_markdown(vault_root)
    summary_mtime = graph_summary_mtime(summary_path)
    state.update(
        {
            "updated_at": utc_now_iso(),
            "last_graph_rebuild_at": utc_now_iso(),
            "last_graph_job_id": job_id,
            "last_graph_parent_question_id": parent_question_id,
            "latest_vault_mtime": latest_mtime,
            "latest_vault_path": latest_path,
            "graph_summary_path": str(summary_path.resolve()),
            "graph_summary_mtime": summary_mtime,
        }
    )
    write_graph_freshness(state, state_path)
    return current_graph_freshness(vault_root=vault_root, summary_path=summary_path, state_path=state_path)
