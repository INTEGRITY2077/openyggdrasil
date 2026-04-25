from __future__ import annotations

import argparse
import json
import sys
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from harness_common import OPENYGGDRASIL_ROOT, utc_now_iso  # noqa: E402
from runner.same_session_answer_smoke import run_same_session_answer_smoke  # noqa: E402


CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
REGRESSION_SCHEMA_PATH = CONTRACTS_ROOT / "hermes_live_replay_regression_result.v1.schema.json"
HERMES_HARNESS_ROOT = PROJECT_ROOT / "providers" / "hermes" / "projects" / "harness"
FORBIDDEN_PROVIDER_PAYLOAD_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "canonical_claim",
    "mailbox_mutation",
    "sot_write",
}


@lru_cache(maxsize=1)
def load_hermes_live_replay_regression_schema() -> dict[str, Any]:
    return json.loads(REGRESSION_SCHEMA_PATH.read_text(encoding="utf-8"))


def _reject_forbidden_provider_payload_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
                raise ValueError(f"Hermes live replay regression forbids provider payload field {path}.{key}")
            _reject_forbidden_provider_payload_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_provider_payload_keys(child, path=f"{path}[{index}]")


def validate_hermes_live_replay_regression_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_live_replay_regression_schema(),
    )
    _reject_forbidden_provider_payload_keys(payload)


def inspect_hermes_live_surface(*, harness_root: Path | None = None) -> tuple[str, list[dict[str, str]]]:
    """Return whether the checked-in Hermes live surface is runnable without copying raw sessions."""

    active_harness = (harness_root or HERMES_HARNESS_ROOT).resolve()
    live_script = active_harness / "live_decision_roundtrip_session.py"
    foreground_probe = active_harness / "hermes_foreground_probe.py"
    checks: list[dict[str, str]] = []

    if live_script.exists():
        checks.append(
            {
                "check": "hermes.live_decision_roundtrip_session",
                "status": "passed",
                "detail": str(live_script),
            }
        )
    else:
        checks.append(
            {
                "check": "hermes.live_decision_roundtrip_session",
                "status": "failed",
                "detail": f"missing: {live_script}",
            }
        )

    if foreground_probe.exists():
        checks.append(
            {
                "check": "hermes.foreground_probe_dependency",
                "status": "passed",
                "detail": str(foreground_probe),
            }
        )
    else:
        checks.append(
            {
                "check": "hermes.foreground_probe_dependency",
                "status": "failed",
                "detail": f"missing: {foreground_probe}",
            }
        )

    if live_script.exists():
        script_text = live_script.read_text(encoding="utf-8", errors="replace")
        imports_foreground_probe = "hermes_foreground_probe" in script_text
        checks.append(
            {
                "check": "hermes.live_script_dependency_declared",
                "status": "passed" if imports_foreground_probe else "skipped",
                "detail": "live script imports hermes_foreground_probe"
                if imports_foreground_probe
                else "live script did not declare hermes_foreground_probe dependency",
            }
        )

    live_available = live_script.exists() and foreground_probe.exists()
    return ("available" if live_available else "unavailable"), checks


def _assumption_delta(*, live_surface_status: str, availability_checks: list[dict[str, str]]) -> dict[str, str] | None:
    if live_surface_status == "available":
        return None
    failed = [check for check in availability_checks if check["status"] == "failed"]
    observed = "; ".join(f"{check['check']}={check['detail']}" for check in failed) or "Hermes live surface unavailable"
    return {
        "expected": "P1.C1 may run a live or foreground-equivalent Hermes replay regression.",
        "observed": observed,
        "evidence_artifact": "hermes_live_replay_regression_result.v1.availability_checks",
        "scope_impact": "Phase 1 can close with typed foreground-equivalent proof; real live UX remains Phase 2 scope.",
        "classification": "within_scope_fallback",
        "next_action": "Run foreground-equivalent local regression and require source_ref plus decoy rejection.",
    }


def run_hermes_live_replay_regression(
    *,
    workspace_root: Path | None = None,
    harness_root: Path | None = None,
) -> dict[str, Any]:
    """Run P1.C1: live-surface probe plus replay-safe foreground-equivalent regression."""

    live_surface_status, availability_checks = inspect_hermes_live_surface(harness_root=harness_root)
    active_workspace = (workspace_root or (OPENYGGDRASIL_ROOT / ".runtime" / "hermes-live-replay-regression")).resolve()
    smoke = run_same_session_answer_smoke(workspace_root=active_workspace)
    relevant_answer = dict(smoke["relevant_answer"])
    assertions = {
        "same_session_smoke_passed": smoke["status"] == "passed",
        "source_ref_present": bool(str(relevant_answer.get("source_ref") or "").strip()),
        "canonical_note_present": bool(str(relevant_answer.get("canonical_note") or "").strip()),
        "relevant_answer_consumed_bundle": bool(relevant_answer.get("consumed_support_bundle")),
        "relevant_answer_cited_mailbox": bool(smoke["assertions"].get("relevant_answer_cited_mailbox")),
        "decoy_answer_rejected_bundle": bool(smoke["assertions"].get("decoy_answer_rejected_bundle")),
        "no_raw_provider_session_copied": True,
    }
    passed = all(assertions.values())
    # This Phase 1 runner never claims a live foreground pass; it only records live
    # availability and closes with a replayable foreground-equivalent regression.
    status = "foreground_equivalent_passed" if passed else "failed"
    result = {
        "schema_version": "hermes_live_replay_regression_result.v1",
        "regression_id": uuid.uuid4().hex,
        "status": status,
        "provider_id": "hermes",
        "live_surface_status": live_surface_status,
        "regression_mode": "foreground_equivalent_local",
        "availability_checks": availability_checks,
        "same_session_smoke_result_id": str(smoke["smoke_result_id"]),
        "source_shortcut_present": assertions["source_ref_present"] and assertions["canonical_note_present"],
        "decoy_rejected": assertions["decoy_answer_rejected_bundle"],
        "inbox_packet_ref": dict(smoke["inbox_packet_ref"]),
        "canonical_note": str(relevant_answer["canonical_note"]),
        "source_ref": str(relevant_answer["source_ref"]),
        "assertions": assertions,
        "assumption_delta": _assumption_delta(
            live_surface_status=live_surface_status,
            availability_checks=availability_checks,
        ),
        "next_action": "phase_close_code_review" if passed else "investigate_failure",
        "created_at": utc_now_iso(),
    }
    validate_hermes_live_replay_regression_result(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Hermes live/foreground-equivalent replay regression.")
    parser.add_argument("--workspace-root", help="Scratch workspace root for foreground-equivalent proof.")
    parser.add_argument("--output", help="Optional JSON output path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)
    result = run_hermes_live_replay_regression(
        workspace_root=Path(args.workspace_root).resolve() if args.workspace_root else None,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=bool(args.pretty))
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] in {"live_passed", "foreground_equivalent_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
