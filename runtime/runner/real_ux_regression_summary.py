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

from harness_common import utc_now_iso  # noqa: E402
from runner.real_ux_regression import validate_real_ux_regression_result  # noqa: E402


CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
SUMMARY_SCHEMA_PATH = CONTRACTS_ROOT / "real_ux_regression_summary.v1.schema.json"
FORBIDDEN_SUMMARY_KEYS = {
    "answer_text",
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
def load_real_ux_regression_summary_schema() -> dict[str, Any]:
    return json.loads(SUMMARY_SCHEMA_PATH.read_text(encoding="utf-8"))


def _reject_forbidden_summary_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_SUMMARY_KEYS:
                raise ValueError(f"real UX regression summary forbids field {path}.{key}")
            _reject_forbidden_summary_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_summary_keys(child, path=f"{path}[{index}]")


def validate_real_ux_regression_summary(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_real_ux_regression_summary_schema(),
    )
    _reject_forbidden_summary_keys(payload)


def _load_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"real UX regression result must be an object: {path}")
    validate_real_ux_regression_result(payload)
    return payload


def _boolean_key_lists(values: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    true_keys: list[str] = []
    false_keys: list[str] = []
    for key, value in sorted(values.items()):
        if value is True:
            true_keys.append(str(key))
        elif value is False:
            false_keys.append(str(key))
    return true_keys, false_keys


def _has_visible_shortcut(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.startswith("missing-") and not text.startswith("not-emitted-")


def summarize_real_ux_regression_results(result_paths: list[Path]) -> dict[str, Any]:
    if not result_paths:
        raise ValueError("At least one real UX regression result path is required")

    scenario_statuses: list[dict[str, Any]] = []
    source_shortcut_matrix: list[dict[str, Any]] = []
    no_raw_flags: list[bool] = []
    passed_count = 0

    for path in result_paths:
        result = _load_result(path.resolve())
        if result["status"] == "passed":
            passed_count += 1

        assertions_true, assertions_false = _boolean_key_lists(dict(result.get("assertions") or {}))
        _, scenario_assertions_false = _boolean_key_lists(dict(result.get("scenario_specific_assertions") or {}))
        provider_answer = dict(result.get("provider_answer") or {})
        source_shortcut = dict(result.get("source_shortcut") or {})
        no_raw_flags.append("no_provider_raw_session_copied" in assertions_true)

        scenario_statuses.append(
            {
                "scenario": str(result["scenario"]),
                "status": str(result["status"]),
                "provider_id": str(result["provider_id"]),
                "regression_mode": str(result["regression_mode"]),
                "next_action": str(result["next_action"]),
                "reason_codes": [str(code) for code in provider_answer.get("reason_codes") or []],
                "assertions_true": assertions_true,
                "assertions_false": assertions_false,
                "scenario_assertions_false": scenario_assertions_false,
                "output_path": str(path.resolve()),
            }
        )
        source_shortcut_matrix.append(
            {
                "scenario": str(result["scenario"]),
                "has_canonical_note": _has_visible_shortcut(source_shortcut.get("canonical_note")),
                "has_provenance_note": _has_visible_shortcut(source_shortcut.get("provenance_note")),
                "has_source_ref": _has_visible_shortcut(source_shortcut.get("source_ref")),
                "origin_shortcut_exists": bool(source_shortcut.get("origin_shortcut_exists")),
            }
        )

    failed_count = len(result_paths) - passed_count
    safety = {
        "no_provider_raw_session_copied_all": all(no_raw_flags),
        "answer_text_excluded": True,
        "provider_raw_payload_keys_excluded": True,
        "summarized_without_raw_transcript": True,
    }
    summary = {
        "schema_version": "real_ux_regression_summary.v1",
        "summary_id": uuid.uuid4().hex,
        "result_count": len(result_paths),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "scenario_statuses": scenario_statuses,
        "source_shortcut_matrix": source_shortcut_matrix,
        "safety": safety,
        "next_action": "phase_close_code_review" if failed_count == 0 and all(safety.values()) else "investigate_failure",
        "created_at": utc_now_iso(),
    }
    validate_real_ux_regression_summary(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize OpenYggdrasil Phase 2 real UX regression results without raw transcripts."
    )
    parser.add_argument("--result", action="append", required=True, help="Path to a real UX regression result JSON.")
    parser.add_argument("--output", help="Optional JSON summary output path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)
    summary = summarize_real_ux_regression_results([Path(value).resolve() for value in args.result])
    rendered = json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=bool(args.pretty))
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if summary["next_action"] == "phase_close_code_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
