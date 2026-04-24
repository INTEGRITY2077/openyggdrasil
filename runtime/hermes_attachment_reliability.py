from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from hermes_foreground_probe import run_hermes_foreground_probe


def summarize_probe_proof(proof: dict[str, Any]) -> dict[str, Any]:
    turns = list(proof.get("turns") or [])
    attachment_summary = proof.get("attachment_summary") or {}
    repairs = list(proof.get("attachment_repairs") or [])
    invalid_rows = list(attachment_summary.get("invalid_rows") or [])
    hermes_rows = list(attachment_summary.get("hermes_profile_rows") or [])
    clean_turns = sum(1 for turn in turns if turn.get("returncode") == 0)
    return {
        "status": proof.get("status"),
        "attached": proof.get("status") == "attached",
        "turn_count": len(turns),
        "clean_turn_count": clean_turns,
        "invalid_row_count": len(invalid_rows),
        "repair_count": len(repairs),
        "attached_session_count": len(hermes_rows),
        "latest_turn_delta_count": max((int(row.get("turn_delta_count") or 0) for row in hermes_rows), default=0),
    }


def aggregate_probe_summaries(summaries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(summaries)
    total = len(rows)
    attached = sum(1 for row in rows if row.get("attached"))
    invalid = sum(int(row.get("invalid_row_count") or 0) for row in rows)
    repairs = sum(int(row.get("repair_count") or 0) for row in rows)
    clean_turn_runs = sum(1 for row in rows if row.get("turn_count") == row.get("clean_turn_count"))
    return {
        "run_count": total,
        "attached_count": attached,
        "attach_success_rate": (attached / total) if total else 0.0,
        "invalid_row_total": invalid,
        "repair_total": repairs,
        "clean_turn_run_count": clean_turn_runs,
    }


def prove_attachment_reliability(
    *,
    iterations: int,
    probe_profile: str,
    clone_from: str,
) -> dict[str, Any]:
    proofs: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for _ in range(iterations):
        proof = run_hermes_foreground_probe(probe_profile=probe_profile, clone_from=clone_from)
        proofs.append(proof)
        summaries.append(summarize_probe_proof(proof))
    return {
        "iterations": iterations,
        "probe_profile": probe_profile,
        "clone_from": clone_from,
        "summaries": summaries,
        "aggregate": aggregate_probe_summaries(summaries),
        "proofs": proofs,
    }


def write_reliability_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
