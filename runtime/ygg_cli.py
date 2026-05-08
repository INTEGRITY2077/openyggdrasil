from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence

RUNTIME_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = RUNTIME_ROOT.parent

if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

DEFAULT_PROVIDER_ID = "hermes"
DEFAULT_PROVIDER_PROFILE = "openyggdrasil-provider"
DEFAULT_PROVIDER_SESSION_ID = "ygg-pro1"
DEFAULT_HEALTHCHECK_SESSION_ID = "ygg-doctor-smoke"

CommandRunner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]

ROLE_SPECS: dict[str, dict[str, str | None]] = {
    "pro1": {
        "display_name": "Provider Lane 1",
        "user_command": "ygg pro1",
        "tmux_session": "ygg-pro1",
        "internal_id": "PRO1",
        "mailbox_key": None,
    },
    "ms1": {
        "display_name": "MS1 (Memory Saver)",
        "user_command": "ygg ms1",
        "tmux_session": "ygg-op1",
        "internal_id": "OP1",
        "mailbox_key": "OP1",
    },
    "mf1": {
        "display_name": "MF1 (Memory Finder)",
        "user_command": "ygg mf1",
        "tmux_session": "ygg-op2",
        "internal_id": "OP2",
        "mailbox_key": "OP2",
    },
}


def _run_command(command: Sequence[str], timeout_seconds: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )


def _workspace_root(value: str | None = None) -> Path:
    return Path(value or os.environ.get("YGG_WORKSPACE") or PROJECT_ROOT).resolve()


def _state_dir(value: str | None = None) -> Path:
    return Path(value or os.environ.get("YGG_STATE_DIR") or (Path.home() / ".yggdrasil")).resolve()


def _provider_id() -> str:
    return os.environ.get("OY_PROVIDER_ID", DEFAULT_PROVIDER_ID).strip() or DEFAULT_PROVIDER_ID


def _provider_profile(provider_id: str) -> str:
    configured = os.environ.get("OY_PROVIDER_PROFILE", "").strip()
    if configured:
        return configured
    if provider_id == DEFAULT_PROVIDER_ID:
        return DEFAULT_PROVIDER_PROFILE
    return f"openyggdrasil-{provider_id}"


def _provider_session_id() -> str:
    return os.environ.get("OY_PROVIDER_SESSION_ID", DEFAULT_PROVIDER_SESSION_ID).strip() or DEFAULT_PROVIDER_SESSION_ID


def _safe_component(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value.strip())
    return cleaned or "unknown"


def _session_uid(provider_id: str, provider_profile: str, provider_session_id: str) -> str:
    return ":".join(
        [
            _safe_component(provider_id),
            _safe_component(provider_profile),
            _safe_component(provider_session_id),
        ]
    )


def _session_uid_path_component(session_uid: str) -> str:
    return _safe_component(session_uid)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = {"_unparseable": True, "_raw": line[:500]}
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _tmux_available() -> bool:
    return shutil.which("tmux") is not None


def _tmux_has_session(session_name: str, *, runner: CommandRunner = _run_command) -> bool:
    result = runner(["tmux", "has-session", "-t", session_name], 5)
    return result.returncode == 0


def _tmux_session_attached(session_name: str, *, runner: CommandRunner = _run_command) -> bool | None:
    result = runner(["tmux", "display-message", "-p", "-t", session_name, "#{session_attached}"], 5)
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    if text == "1":
        return True
    if text == "0":
        return False
    return None


def _mailbox_summary(*, state_dir: Path, mailbox_key: str) -> dict[str, Any]:
    mailbox = state_dir / "sessions" / mailbox_key
    if mailbox_key == "OP1":
        intent_file = mailbox / "intents.jsonl"
        receipt_file = mailbox / "receipts.jsonl"
    else:
        intent_file = mailbox / "queries.jsonl"
        receipt_file = mailbox / "query_receipts.jsonl"

    intents = _read_jsonl(intent_file)
    receipts = _read_jsonl(receipt_file)
    latest_receipt = receipts[-1] if receipts else None
    pending = max(0, len(intents) - len(receipts))
    produced_count = latest_receipt.get("produced_count") if isinstance(latest_receipt, dict) else None
    support_bundle = None
    if isinstance(latest_receipt, dict):
        bundle = latest_receipt.get("bundle")
        if isinstance(bundle, dict):
            support_bundle = bundle.get("support_bundle")
    support_paths = support_bundle.get("source_paths") if isinstance(support_bundle, dict) else []
    return {
        "mailbox": str(mailbox),
        "intent_count": len(intents),
        "receipt_count": len(receipts),
        "pending_approx": pending,
        "latest_receipt_id": latest_receipt.get("receipt_id") if isinstance(latest_receipt, dict) else None,
        "latest_reply_to": latest_receipt.get("in_reply_to") if isinstance(latest_receipt, dict) else None,
        "latest_produced_count": produced_count,
        "support_bundle_schema": support_bundle.get("schema_version") if isinstance(support_bundle, dict) else None,
        "support_facts_count": len(support_bundle.get("support_facts", [])) if isinstance(support_bundle, dict) else 0,
        "source_paths_count": len(support_paths) if isinstance(support_paths, list) else 0,
        "typed_unavailable_present": bool(support_bundle.get("typed_unavailable")) if isinstance(support_bundle, dict) else False,
    }


def _provider_inbox_summary(*, workspace_root: Path) -> dict[str, Any]:
    provider_id = _provider_id()
    provider_profile = _provider_profile(provider_id)
    provider_session_id = _provider_session_id()
    session_uid = _session_uid(provider_id, provider_profile, provider_session_id)
    inbox_path = (
        workspace_root
        / ".yggdrasil"
        / "inbox"
        / _safe_component(provider_id)
        / _safe_component(provider_profile)
        / f"{_session_uid_path_component(session_uid)}.jsonl"
    )
    packets = _read_jsonl(inbox_path)
    latest_packet = packets[-1] if packets else {}
    operator_briefs = [row for row in packets if row.get("packet_type") == "operator_brief"]
    latest = operator_briefs[-1] if operator_briefs else latest_packet
    payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else latest
    handoff = payload.get("provider_inbox_handoff") if isinstance(payload, dict) else None
    op2_support = payload.get("op2_support_metadata") if isinstance(payload, dict) else None
    recall_digest = op2_support.get("recall_digest") if isinstance(op2_support, dict) else None
    return {
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "inbox_path": str(inbox_path),
        "packet_count": len(packets),
        "operator_brief_count": len(operator_briefs),
        "latest_packet_type": latest.get("packet_type") if isinstance(latest, dict) else None,
        "heartbeat_cpr_status": payload.get("heartbeat_cpr_status") if isinstance(payload, dict) else None,
        "handoff_status": handoff.get("handoff_status") if isinstance(handoff, dict) else payload.get("handoff_status") if isinstance(payload, dict) else None,
        "manual_prompt_injection_required": (
            handoff.get("manual_prompt_injection_required")
            if isinstance(handoff, dict)
            else payload.get("manual_prompt_injection_required")
            if isinstance(payload, dict)
            else None
        ),
        "support_bundle_schema": op2_support.get("support_schema_version") if isinstance(op2_support, dict) else None,
        "support_facts_count": (
            op2_support.get("support_facts_count")
            if isinstance(op2_support, dict) and op2_support.get("support_facts_count") is not None
            else len(op2_support.get("support_facts", []))
            if isinstance(op2_support, dict)
            else None
        ),
        "source_paths_count": len(op2_support.get("source_paths", [])) if isinstance(op2_support, dict) else 0,
        "recall_digest_status": recall_digest.get("status") if isinstance(recall_digest, dict) else None,
        "typed_unavailable_present": bool(op2_support.get("typed_unavailable_present")) if isinstance(op2_support, dict) else None,
    }


def build_status_report(
    *,
    target: str | None = None,
    workspace_root: Path | None = None,
    state_dir: Path | None = None,
    runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    workspace = _workspace_root(str(workspace_root) if workspace_root else None)
    state = _state_dir(str(state_dir) if state_dir else None)
    selected = target.lower() if target else None
    if selected and selected not in ROLE_SPECS:
        return _typed_unavailable("unsupported_status_target", f"Unknown status target: {target}")

    tmux_present = _tmux_available()
    lane_rows: list[dict[str, Any]] = []
    for role, spec in ROLE_SPECS.items():
        session = str(spec["tmux_session"])
        exists = tmux_present and _tmux_has_session(session, runner=runner)
        row: dict[str, Any] = {
            "role": role,
            "display_name": spec["display_name"],
            "user_command": spec["user_command"],
            "internal_id": spec["internal_id"],
            "tmux_session": session,
            "tmux_present": exists,
            "tmux_attached": _tmux_session_attached(session, runner=runner) if exists else None,
            "witness_role": "tmux_live_witness_not_sot",
        }
        mailbox_key = spec.get("mailbox_key")
        if mailbox_key:
            row["mailbox_summary"] = _mailbox_summary(state_dir=state, mailbox_key=str(mailbox_key))
        lane_rows.append(row)

    visible_rows = [row for row in lane_rows if selected is None or row["role"] == selected]
    missing = [row["role"] for row in lane_rows if not row["tmux_present"]]
    live_ready = tmux_present and not missing
    report: dict[str, Any] = {
        "schema_version": "ygg_lifecycle_status.v1",
        "status": "ready" if live_ready else "not_ready",
        "target": selected or "provider_unit_1",
        "workspace_root": str(workspace),
        "state_dir": str(state),
        "tmux_binary_present": tmux_present,
        "live_witness_status": "ready" if live_ready else "not_ready",
        "missing_witness_roles": missing,
        "lanes": visible_rows,
        "provider_cpr": _provider_inbox_summary(workspace_root=workspace),
        "next_action": (
            "Use ygg pro1 / ygg ms1 / ygg mf1 to inspect the live Provider Unit."
            if live_ready
            else "Start or restore the missing tmux witness sessions before claiming live UX proof."
        ),
        "hard_nonclaims": {
            "tmux_is_sot": False,
            "tmux_capture_alone_is_pass": False,
            "stale_poc_sessions_are_fresh_product_ux": False,
            "readme_scorecard_promotion_allowed": False,
        },
    }
    if not live_ready:
        report["typed_unavailable"] = {
            "schema_version": "typed_unavailable.v1",
            "status": "typed_unavailable",
            "reason_code": "tmux_live_witness_not_ready",
            "blocked_stage": "provider_unit_live_ux_proof",
            "missing_witness_roles": missing,
            "fabricated_answer": False,
            "raw_provider_material_included": False,
        }
    return report


def build_doctor_report(
    *,
    workspace_root: Path | None = None,
    state_dir: Path | None = None,
    write_marker: bool = True,
    runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    workspace = _workspace_root(str(workspace_root) if workspace_root else None)
    status_report = build_status_report(workspace_root=workspace, state_dir=state_dir, runner=runner)
    provider_id = _provider_id()
    provider_profile = _provider_profile(provider_id)
    live_provider_session_id = _provider_session_id()
    configured_healthcheck_session_id = os.environ.get("OY_HEALTHCHECK_SESSION_ID", "").strip()
    if configured_healthcheck_session_id:
        healthcheck_session_id = configured_healthcheck_session_id
    elif write_marker:
        healthcheck_session_id = DEFAULT_HEALTHCHECK_SESSION_ID
    else:
        healthcheck_session_id = f"{DEFAULT_HEALTHCHECK_SESSION_ID}-{uuid.uuid4().hex[:8]}"
    install_surface = (
        os.environ.get("OY_INSTALL_SURFACE", "").strip()
        or ("hermes_profile_skill" if provider_id == DEFAULT_PROVIDER_ID else "provider_native_skill")
    )
    try:
        from attachments.provider_cold_start_healthcheck import run_provider_cold_start_healthcheck

        healthcheck = run_provider_cold_start_healthcheck(
            workspace_root=workspace,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=healthcheck_session_id,
            install_surface=install_surface,
            force=not write_marker,
            write_marker=write_marker,
        )
    except Exception as exc:  # noqa: BLE001
        healthcheck = {
            "schema_version": "provider_cold_start_healthcheck.v1",
            "status": "not_ready",
            "admission_allowed": False,
            "reason_code": "provider_cold_start_healthcheck_unavailable",
            "error_type": exc.__class__.__name__,
            "provider_id": provider_id,
            "provider_profile": provider_profile,
            "provider_session_id": healthcheck_session_id,
            "next_action": "inspect_provider_cold_start_healthcheck_import_or_runtime_dependencies",
        }
    return {
        "schema_version": "ygg_lifecycle_doctor.v1",
        "status": "ready" if status_report["status"] == "ready" and healthcheck.get("admission_allowed") else "not_ready",
        "live_provider_session_id": live_provider_session_id,
        "healthcheck_session_id": healthcheck_session_id,
        "provider_healthcheck": healthcheck,
        "live_witness": status_report,
        "next_action": status_report["next_action"],
        "hard_nonclaims": status_report["hard_nonclaims"],
    }


def _typed_unavailable(reason_code: str, detail: str) -> dict[str, Any]:
    return {
        "schema_version": "typed_unavailable.v1",
        "status": "typed_unavailable",
        "reason_code": reason_code,
        "detail": detail,
        "fabricated_answer": False,
        "raw_provider_material_included": False,
    }


def build_attach_action(
    target: str,
    *,
    inside_tmux: bool | None = None,
    runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    role = target.lower()
    spec = ROLE_SPECS.get(role)
    if not spec:
        return _typed_unavailable("unsupported_attach_target", f"Unknown attach target: {target}")
    session = str(spec["tmux_session"])
    if not _tmux_available():
        return _typed_unavailable("tmux_binary_missing", "tmux is required for the live witness attach surface")
    if not _tmux_has_session(session, runner=runner):
        return {
            **_typed_unavailable("tmux_session_missing", f"Missing tmux witness session: {session}"),
            "target": role,
            "user_command": spec["user_command"],
            "tmux_session": session,
        }
    in_tmux = bool(os.environ.get("TMUX")) if inside_tmux is None else inside_tmux
    command = ["tmux", "switch-client", "-t", session] if in_tmux else ["tmux", "attach", "-t", session]
    return {
        "schema_version": "ygg_lifecycle_attach_action.v1",
        "status": "ready",
        "target": role,
        "display_name": spec["display_name"],
        "user_command": spec["user_command"],
        "tmux_session": session,
        "attach_mode": "switch-client" if in_tmux else "attach",
        "command": command,
        "hard_nonclaims": {
            "tmux_is_sot": False,
            "raw_tmux_stdin_is_memory_lane_talk": False,
        },
    }


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _render_status_text(payload: dict[str, Any]) -> str:
    lines = [
        "[YGG SESSION GROUP HEALTH WORKFLOW]",
        "now: inspect Provider Unit 1 live witness field",
        f"watching: workspace={payload['workspace_root']}; state={payload['state_dir']}",
        f"created: live_witness_status={payload['live_witness_status']}",
    ]
    for lane in payload["lanes"]:
        lines.append(
            "lane: {role} user={user} tmux={tmux} present={present} attached={attached}".format(
                role=lane["display_name"],
                user=lane["user_command"],
                tmux=lane["tmux_session"],
                present=str(lane["tmux_present"]).lower(),
                attached=lane["tmux_attached"],
            )
        )
        mailbox = lane.get("mailbox_summary")
        if mailbox:
            lines.append(
                "mailbox: intents={intent_count} receipts={receipt_count} pending~={pending_approx} latest_receipt={latest_receipt_id}".format(
                    **mailbox
                )
            )
    cpr = payload["provider_cpr"]
    lines.append(
        "provider_cpr: packets={packet_count} heartbeat={heartbeat_cpr_status} handoff={handoff_status} manual_prompt_injection_required={manual_prompt_injection_required}".format(
            **cpr
        )
    )
    if "typed_unavailable" in payload:
        lines.append(f"typed_unavailable: {payload['typed_unavailable']['reason_code']}")
    lines.append(f"next_action: {payload['next_action']}")
    lines.append(f"status: {payload['status']}")
    lines.append("hard_nonclaims: tmux_is_sot=false; tmux_capture_alone_is_pass=false")
    return "\n".join(lines)


def _render_doctor_text(payload: dict[str, Any]) -> str:
    health = payload["provider_healthcheck"]
    witness = payload["live_witness"]
    lines = [
        "[YGG DOCTOR WORKFLOW]",
        "now: check Provider Unit 1 lifecycle readiness",
        f"provider_healthcheck={health.get('status')} admission_allowed={health.get('admission_allowed')}",
        f"live_witness_status={witness.get('live_witness_status')}",
        f"next_action: {payload['next_action']}",
        f"status: {payload['status']}",
        "hard_nonclaims: doctor is readiness evidence, not production UX PASS",
    ]
    return "\n".join(lines)


def _execute_attach(action: dict[str, Any], *, dry_run: bool = False) -> int:
    if action.get("status") != "ready":
        _print_json(action)
        return 2
    if dry_run:
        _print_json(action)
        return 0
    command = list(action["command"])
    if action["attach_mode"] == "switch-client":
        result = _run_command(command, 10)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        return result.returncode
    os.execvp(command[0], command)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ygg", description="OpenYggdrasil Provider Unit lifecycle CLI")
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="Check Provider Unit 1 lifecycle readiness")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    doctor.add_argument("--no-write-marker", action="store_true", help="Do not write healthcheck marker files")

    status = subparsers.add_parser("status", help="Inspect Provider Unit 1 live witness status")
    status.add_argument("target", nargs="?", choices=sorted(ROLE_SPECS), help="Optional lane: pro1, ms1, or mf1")
    status.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    for role in sorted(ROLE_SPECS):
        lane = subparsers.add_parser(role, help=f"Attach or inspect {ROLE_SPECS[role]['display_name']}")
        lane.add_argument("--doctor", action="store_true", help="Run doctor instead of attaching")
        lane.add_argument("--status", action="store_true", help="Show lane status instead of attaching")
        lane.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
        lane.add_argument("--dry-run", action="store_true", help="Show the tmux attach/switch action without executing it")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "doctor":
        payload = build_doctor_report(write_marker=not args.no_write_marker)
        if args.json:
            _print_json(payload)
        else:
            print(_render_doctor_text(payload))
        return 0 if payload["status"] == "ready" else 1

    if args.command == "status":
        payload = build_status_report(target=args.target)
        if args.json:
            _print_json(payload)
        else:
            print(_render_status_text(payload))
        return 0 if payload["status"] == "ready" else 1

    if args.command in ROLE_SPECS:
        if args.doctor:
            payload = build_doctor_report(write_marker=True)
            if args.json:
                _print_json(payload)
            else:
                print(_render_doctor_text(payload))
            return 0 if payload["status"] == "ready" else 1
        if args.status:
            payload = build_status_report(target=args.command)
            if args.json:
                _print_json(payload)
            else:
                print(_render_status_text(payload))
            return 0 if payload["status"] == "ready" else 1
        action = build_attach_action(args.command)
        return _execute_attach(action, dry_run=args.dry_run)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
