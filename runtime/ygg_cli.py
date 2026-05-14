from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from runtime.cli.ygg import main


Runner = Callable[[Sequence[str], int], subprocess.CompletedProcess]


def _default_runner(command: Sequence[str], timeout_seconds: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(list(command), capture_output=True, text=True, timeout=timeout_seconds)


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _tmux_has_session(session: str, runner: Runner | None = None) -> bool:
    if not shutil.which("tmux"):
        return False
    run = runner or _default_runner
    result = run(["tmux", "has-session", "-t", session], 5)
    return result.returncode == 0


def _mailbox_summary(state_dir: Path, role: str) -> dict[str, Any]:
    mailbox_name = "MS1" if role == "ms1" else "MF1"
    mailbox = state_dir / "sessions" / mailbox_name
    if role == "ms1":
        intents = _jsonl_rows(mailbox / "intents.jsonl")
        receipts = _jsonl_rows(mailbox / "receipts.jsonl")
        replied = {str(row.get("in_reply_to") or "") for row in receipts}
        return {
            "mailbox": mailbox_name,
            "intent_count": len(intents),
            "receipt_count": len(receipts),
            "pending_approx": sum(1 for row in intents if str(row.get("mail_id") or "") not in replied),
        }
    queries = _jsonl_rows(mailbox / "queries.jsonl")
    receipts = _jsonl_rows(mailbox / "query_receipts.jsonl")
    latest = receipts[-1] if receipts else {}
    bundle = latest.get("bundle") if isinstance(latest, Mapping) else {}
    support_bundle = bundle.get("support_bundle") if isinstance(bundle, Mapping) else {}
    return {
        "mailbox": mailbox_name,
        "query_count": len(queries),
        "receipt_count": len(receipts),
        "support_bundle_schema": support_bundle.get("schema_version") if isinstance(support_bundle, Mapping) else None,
        "support_fact_count": len(support_bundle.get("support_facts") or []) if isinstance(support_bundle, Mapping) else 0,
        "source_path_count": len(support_bundle.get("source_paths") or []) if isinstance(support_bundle, Mapping) else 0,
    }


def _provider_cpr_summary(workspace_root: Path) -> dict[str, Any]:
    inbox = (
        workspace_root
        / ".yggdrasil"
        / "inbox"
        / "hermes"
        / "openyggdrasil-provider"
        / "hermes_openyggdrasil-provider_ygg-pro1.jsonl"
    )
    packets = _jsonl_rows(inbox)
    briefs = [row for row in packets if row.get("packet_type") == "operator_brief"]
    latest = briefs[-1] if briefs else {}
    payload = latest.get("payload") if isinstance(latest.get("payload"), Mapping) else latest
    handoff = payload.get("provider_inbox_handoff") if isinstance(payload, Mapping) else {}
    support = payload.get("mf1_support_metadata") if isinstance(payload, Mapping) else {}
    support_facts = support.get("support_facts") if isinstance(support, Mapping) else []
    source_paths = support.get("source_paths") if isinstance(support, Mapping) else []
    return {
        "packet_count": len(packets),
        "operator_brief_count": len(briefs),
        "heartbeat_cpr_status": payload.get("heartbeat_cpr_status") if isinstance(payload, Mapping) else None,
        "handoff_status": (
            handoff.get("handoff_status")
            if isinstance(handoff, Mapping)
            else payload.get("handoff_status") if isinstance(payload, Mapping) else None
        ),
        "manual_prompt_injection_required": (
            handoff.get("manual_prompt_injection_required")
            if isinstance(handoff, Mapping)
            else payload.get("manual_prompt_injection_required") if isinstance(payload, Mapping) else None
        ),
        "support_facts_count": (
            support.get("support_facts_count")
            if isinstance(support, Mapping) and support.get("support_facts_count") is not None
            else len(support_facts) if isinstance(support_facts, list) else 0
        ),
        "source_paths_count": len(source_paths) if isinstance(source_paths, list) else 0,
    }


def build_status_report(
    *,
    workspace_root: str | Path,
    state_dir: str | Path,
    runner: Runner | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace_root)
    state = Path(state_dir)
    lane_defs = [
        ("pro1", "ygg pro1", "ygg-pro1"),
        ("ms1", "ygg ms1", "ygg-ms1"),
        ("mf1", "ygg mf1", "ygg-mf1"),
    ]
    lanes: list[dict[str, Any]] = []
    missing: list[str] = []
    for role, user_command, session in lane_defs:
        present = _tmux_has_session(session, runner)
        if not present:
            missing.append(role)
        row = {
            "role": role,
            "user_command": user_command,
            "tmux_session": session,
            "tmux_witness": "present" if present else "missing",
        }
        if role in {"ms1", "mf1"}:
            row["mailbox_summary"] = _mailbox_summary(state, role)
        lanes.append(row)
    status = "ready" if not missing else "not_ready"
    report: dict[str, Any] = {
        "schema_version": "ygg_status_report.v1",
        "status": status,
        "lanes": lanes,
        "missing_witness_roles": missing,
        "provider_cpr": _provider_cpr_summary(workspace),
        "hard_nonclaims": {
            "tmux_is_sot": False,
            "pane_text_is_proof": False,
            "production_ready_claimed": False,
        },
    }
    if missing:
        report["typed_unavailable"] = {
            "schema_version": "typed_unavailable.v1",
            "reason_code": "tmux_live_witness_not_ready",
            "missing_roles": missing,
        }
    return report


def build_attach_action(
    role: str,
    *,
    inside_tmux: bool = False,
    runner: Runner | None = None,
) -> dict[str, Any]:
    key = str(role or "").strip().lower()
    session_map = {"pro1": "ygg-pro1", "ms1": "ygg-ms1", "mf1": "ygg-mf1"}
    session = session_map.get(key, key)
    if not _tmux_has_session(session, runner):
        return {
            "schema_version": "ygg_attach_action.v1",
            "status": "typed_unavailable",
            "reason_code": "tmux_session_missing",
            "tmux_session": session,
        }
    command = ["tmux", "switch-client", "-t", session] if inside_tmux else ["tmux", "attach", "-t", session]
    return {
        "schema_version": "ygg_attach_action.v1",
        "status": "ready",
        "tmux_session": session,
        "attach_mode": "switch-client" if inside_tmux else "attach",
        "command": command,
    }


__all__ = ["build_attach_action", "build_status_report", "main", "shutil"]


if __name__ == "__main__":
    raise SystemExit(main())
