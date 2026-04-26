from __future__ import annotations

import base64
import json
import re
import shutil
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import jsonschema

from admission.decision_contracts import validate_mailbox_support_result
from delivery.support_bundle import validate_support_bundle
from harness_common import DEFAULT_VAULT, utc_now_iso
from common.map_identity import build_claim_id, build_page_id, build_topic_id
from cultivation.vault_record_lifecycle import validate_vault_record_lifecycle
from evaluation.promotion_worthiness import (
    DEFAULT_HERMES_BIN,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    _run_wsl_python,
)
from placement.topic_episode_placement_engine import list_existing_topics
from provenance.provenance_store import parse_provenance_records, provenance_page_path
from retrieval.origin_shortcut_roundtrip import (
    follow_origin_shortcut,
    validate_origin_shortcut_result,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
PATHFINDER_SCHEMA_PATH = OPENYGGDRASIL_ROOT / "contracts" / "pathfinder.v1.schema.json"
PATHFINDER_RETRIEVAL_RESULT_SCHEMA_PATH = (
    OPENYGGDRASIL_ROOT / "contracts" / "pathfinder_retrieval_result.v1.schema.json"
)
ACTIVE_LIFECYCLE_STATE = "ACTIVE"
EXCLUDED_RETRIEVAL_LIFECYCLE_STATES = {"STALE", "SUPERSEDED"}


@lru_cache(maxsize=1)
def load_pathfinder_schema() -> dict[str, Any]:
    return json.loads(PATHFINDER_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_pathfinder_retrieval_result_schema() -> dict[str, Any]:
    return json.loads(PATHFINDER_RETRIEVAL_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_pathfinder_bundle(bundle: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(bundle), schema=load_pathfinder_schema())


def validate_pathfinder_retrieval_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_pathfinder_retrieval_result_schema())


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


def _non_empty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _non_empty_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    rows: list[str] = []
    for value in values:
        text = _non_empty(value)
        if text and text not in rows:
            rows.append(text)
    return rows


def _support_bundle_shortcuts(support_bundle: Mapping[str, Any]) -> dict[str, Any]:
    pathfinder_bundle = support_bundle.get("pathfinder_bundle")
    pathfinder_source_paths: list[str] = []
    if isinstance(pathfinder_bundle, Mapping):
        pathfinder_source_paths = _non_empty_strings(pathfinder_bundle.get("source_paths"))
    return {
        "canonical_note": _non_empty(support_bundle.get("canonical_note")),
        "provenance_note": _non_empty(support_bundle.get("provenance_note")),
        "source_paths": _non_empty_strings(support_bundle.get("source_paths")),
        "pathfinder_source_paths": pathfinder_source_paths,
    }


def _mailbox_packet_refs(mailbox_support_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in mailbox_support_result.get("mailbox_packet_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        refs.append(
            {
                "message_id": str(ref.get("message_id") or "").strip(),
                "packet_type": str(ref.get("packet_type") or "").strip(),
                "path_hint": _non_empty(ref.get("path_hint")),
            }
        )
    return [ref for ref in refs if ref["message_id"] and ref["packet_type"]]


def _source_refs(mailbox_support_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in mailbox_support_result.get("source_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        refs.append(
            {
                "kind": str(ref.get("kind") or "provider_session").strip() or "provider_session",
                "path_hint": str(ref.get("path_hint") or "missing-source-ref").strip() or "missing-source-ref",
                "range_hint": ref.get("range_hint"),
                "symlink_hint": ref.get("symlink_hint"),
                "message_id": ref.get("message_id"),
            }
        )
    return refs or [{"kind": "provider_session", "path_hint": "missing-source-ref"}]


def _has_forwarded_source_ref(source_refs: list[dict[str, Any]]) -> bool:
    for ref in source_refs:
        path_hint = str(ref.get("path_hint") or "").strip()
        if path_hint and path_hint != "missing-source-ref":
            return True
    return False


def _topic_key_from_source_path(path_value: str) -> str | None:
    normalized = path_value.replace("\\", "/")
    match = re.search(r"(?:^|/)queries/(?P<topic_key>[^/]+)\.md$", normalized)
    if match:
        return match.group("topic_key")
    return None


def _first_topic_key_from_shortcuts(shortcuts: Mapping[str, Any]) -> str | None:
    candidate_paths = []
    for key in ("canonical_note", "provenance_note"):
        value = _non_empty(shortcuts.get(key))
        if value:
            candidate_paths.append(value)
    candidate_paths.extend(str(item) for item in shortcuts.get("source_paths") or [])
    candidate_paths.extend(str(item) for item in shortcuts.get("pathfinder_source_paths") or [])
    for path_value in candidate_paths:
        topic_key = _topic_key_from_source_path(path_value)
        if topic_key:
            return topic_key
    return None


def _merged_pathfinder_source_paths(
    *,
    support_bundle: Mapping[str, Any],
    shortcuts: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
) -> list[str]:
    merged: list[str] = []
    for key in ("canonical_note", "provenance_note"):
        value = _non_empty(shortcuts.get(key))
        if value and value not in merged:
            merged.append(value)
    for key in ("source_paths", "pathfinder_source_paths"):
        for value in shortcuts.get(key) or []:
            text = _non_empty(value)
            if text and text not in merged:
                merged.append(text)
    if isinstance(origin_shortcut_result, Mapping):
        resolved_path = _non_empty(origin_shortcut_result.get("resolved_path"))
        if resolved_path and resolved_path not in merged:
            merged.append(resolved_path)
    pathfinder_bundle = support_bundle.get("pathfinder_bundle")
    if isinstance(pathfinder_bundle, Mapping):
        for value in pathfinder_bundle.get("source_paths") or []:
            text = _non_empty(value)
            if text and text not in merged:
                merged.append(text)
    return merged


def _support_facts_from_mailbox_support(
    *,
    support_bundle: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
) -> list[str]:
    facts = _non_empty_strings(support_bundle.get("facts"))
    pathfinder_bundle = support_bundle.get("pathfinder_bundle")
    if isinstance(pathfinder_bundle, Mapping):
        for fact in _non_empty_strings(pathfinder_bundle.get("support_facts")):
            if fact not in facts:
                facts.append(fact)
    if isinstance(origin_shortcut_result, Mapping):
        preview = _non_empty(origin_shortcut_result.get("evidence_preview"))
        if preview and preview not in facts:
            facts.append(preview)
    return facts


def _lifecycle_ref(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_record_id": str(record["lifecycle_record_id"]),
        "canonical_record_id": str(record["canonical_record_id"]),
        "lifecycle_state": str(record["lifecycle_state"]),
        "canonical_ref": dict(record["canonical_ref"]),
        "source_refs": [dict(ref) for ref in record["source_refs"]],
        "provenance": dict(record["provenance"]),
        "valid_from": record.get("valid_from"),
        "valid_until": record.get("valid_until"),
        "invalidated_by": dict(record["invalidated_by"]) if isinstance(record.get("invalidated_by"), Mapping) else None,
        "superseded_by": record.get("superseded_by"),
        "superseded_at": record.get("superseded_at"),
        "supersession_reason": record.get("supersession_reason"),
        "archive_trace_refs": [dict(ref) for ref in record["archive_trace_refs"]],
    }


def filter_lifecycle_records_for_retrieval(
    lifecycle_records: Sequence[Mapping[str, Any]] | None,
    *,
    include_historical: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    filtered_inactive = 0
    for record in lifecycle_records or []:
        validate_vault_record_lifecycle(record)
        lifecycle_state = str(record.get("lifecycle_state") or "")
        if lifecycle_state != ACTIVE_LIFECYCLE_STATE and not include_historical:
            filtered_inactive += 1
            continue
        selected.append(_lifecycle_ref(record))
    return selected, filtered_inactive


def _lifecycle_rejection_reason(record: Mapping[str, Any]) -> dict[str, Any] | None:
    lifecycle_state = str(record.get("lifecycle_state") or "")
    if lifecycle_state == "SUPERSEDED":
        return {
            "canonical_record_id": str(record["canonical_record_id"]),
            "lifecycle_state": lifecycle_state,
            "reason_code": "superseded_record_filtered",
            "reason": str(record.get("supersession_reason") or "").strip(),
            "superseded_by": record.get("superseded_by"),
            "invalidated_by": dict(record["invalidated_by"])
            if isinstance(record.get("invalidated_by"), Mapping)
            else None,
        }
    if lifecycle_state == "STALE":
        return {
            "canonical_record_id": str(record["canonical_record_id"]),
            "lifecycle_state": lifecycle_state,
            "reason_code": "stale_record_filtered",
            "reason": str(record.get("supersession_reason") or "").strip(),
            "superseded_by": None,
            "invalidated_by": dict(record["invalidated_by"])
            if isinstance(record.get("invalidated_by"), Mapping)
            else None,
        }
    return None


def measure_lifecycle_rejection_ux_metrics(
    lifecycle_records: Sequence[Mapping[str, Any]] | None,
    *,
    include_historical: bool = False,
) -> dict[str, Any]:
    """Measure UX-FS-04 lifecycle filtering and rejection visibility."""

    selected, inactive_filtered = filter_lifecycle_records_for_retrieval(
        lifecycle_records,
        include_historical=include_historical,
    )
    selected_states = [str(record.get("lifecycle_state") or "") for record in selected]
    stale_false_accept_count = selected_states.count("STALE")
    superseded_false_accept_count = selected_states.count("SUPERSEDED")

    rejection_reasons: list[dict[str, Any]] = []
    rejected_lifecycle_record_count = 0
    for record in lifecycle_records or []:
        validate_vault_record_lifecycle(record)
        lifecycle_state = str(record.get("lifecycle_state") or "")
        if lifecycle_state == ACTIVE_LIFECYCLE_STATE or include_historical:
            continue
        rejected_lifecycle_record_count += 1
        reason = _lifecycle_rejection_reason(record)
        if reason and reason["reason"] and reason["invalidated_by"]:
            rejection_reasons.append(reason)

    if rejected_lifecycle_record_count:
        rejection_reason_coverage: float | str = len(rejection_reasons) / rejected_lifecycle_record_count
    else:
        rejection_reason_coverage = "not_applicable"

    decision = (
        "green_passed"
        if (
            stale_false_accept_count == 0
            and superseded_false_accept_count == 0
            and (
                rejection_reason_coverage == 1.0
                or rejection_reason_coverage == "not_applicable"
            )
        )
        else "red_captured"
    )

    return {
        "surface_id": "UX-FS-04",
        "lifecycle_filter_mode": "historical_including_inactive"
        if include_historical
        else "active_only",
        "stale_false_accept_count": stale_false_accept_count,
        "superseded_false_accept_count": superseded_false_accept_count,
        "rejected_lifecycle_record_count": rejected_lifecycle_record_count,
        "rejection_reason_coverage": rejection_reason_coverage,
        "inactive_records_filtered": inactive_filtered,
        "rejection_reasons": rejection_reasons,
        "decision": decision,
    }


def measure_historical_intent_discriminator_metrics(
    lifecycle_records: Sequence[Mapping[str, Any]] | None,
    *,
    historical_intent: bool,
    selected_lifecycle_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Measure whether inactive memory is used only for historical-intent retrieval."""

    source_records: list[Mapping[str, Any]] = []
    for record in lifecycle_records or []:
        validate_vault_record_lifecycle(record)
        source_records.append(record)

    if selected_lifecycle_records is None:
        selected_records, _ = filter_lifecycle_records_for_retrieval(
            source_records,
            include_historical=historical_intent,
        )
    else:
        selected_records = [dict(record) for record in selected_lifecycle_records]

    candidate_inactive_ids = {
        str(record.get("canonical_record_id") or "")
        for record in source_records
        if str(record.get("lifecycle_state") or "") in EXCLUDED_RETRIEVAL_LIFECYCLE_STATES
    }
    selected_inactive_records = [
        record
        for record in selected_records
        if str(record.get("lifecycle_state") or "") in EXCLUDED_RETRIEVAL_LIFECYCLE_STATES
    ]
    selected_inactive_ids = {
        str(record.get("canonical_record_id") or "")
        for record in selected_inactive_records
    }
    stale_selected_count = sum(
        1 for record in selected_inactive_records if str(record.get("lifecycle_state") or "") == "STALE"
    )
    superseded_selected_count = sum(
        1 for record in selected_inactive_records if str(record.get("lifecycle_state") or "") == "SUPERSEDED"
    )
    stale_false_accept_count = 0 if historical_intent else stale_selected_count
    superseded_false_accept_count = 0 if historical_intent else superseded_selected_count
    historical_records_included = len(selected_inactive_records) if historical_intent else 0
    historical_context_missing_count = (
        max(0, len(candidate_inactive_ids - selected_inactive_ids))
        if historical_intent
        else 0
    )
    inactive_records_filtered = len(candidate_inactive_ids - selected_inactive_ids)

    if historical_records_included:
        visible_historical_records = sum(
            1
            for record in selected_inactive_records
            if record.get("source_refs") and record.get("provenance")
        )
        historical_evidence_visibility: float | str = visible_historical_records / historical_records_included
    else:
        historical_evidence_visibility = "not_applicable"

    if historical_intent:
        decision = (
            "green_passed"
            if (
                stale_false_accept_count == 0
                and superseded_false_accept_count == 0
                and historical_context_missing_count == 0
                and (
                    historical_evidence_visibility == 1.0
                    or historical_evidence_visibility == "not_applicable"
                )
            )
            else "red_captured"
        )
    else:
        decision = (
            "green_passed"
            if stale_false_accept_count == 0 and superseded_false_accept_count == 0
            else "red_captured"
        )

    return {
        "surface_id": "UX-FS-04",
        "scenario_id": "P9-S08",
        "intent_mode": "historical" if historical_intent else "current_truth",
        "historical_intent": historical_intent,
        "inactive_candidate_count": len(candidate_inactive_ids),
        "historical_records_included": historical_records_included,
        "historical_context_missing_count": historical_context_missing_count,
        "inactive_records_filtered": inactive_records_filtered,
        "stale_false_accept_count": stale_false_accept_count,
        "superseded_false_accept_count": superseded_false_accept_count,
        "historical_evidence_visibility": historical_evidence_visibility,
        "decision": decision,
    }


def _pathfinder_bundle_from_mailbox_support(
    *,
    support_bundle: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    nested_bundle = support_bundle.get("pathfinder_bundle")
    if isinstance(nested_bundle, Mapping):
        nested = dict(nested_bundle)
        required_keys = set(load_pathfinder_schema().get("required") or [])
        if required_keys <= set(nested):
            validate_pathfinder_bundle(nested)
            return nested

    shortcuts = _support_bundle_shortcuts(support_bundle)
    source_paths = _merged_pathfinder_source_paths(
        support_bundle=support_bundle,
        shortcuts=shortcuts,
        origin_shortcut_result=origin_shortcut_result,
    )
    topic_key = _first_topic_key_from_shortcuts(shortcuts)
    topic_id = build_topic_id(topic_key) if topic_key else None
    page_id = build_page_id(f"queries/{topic_key}.md") if topic_key else None
    bundle = {
        "schema_version": "pathfinder.v1",
        "query_text": str(support_bundle["query_text"]),
        "anchor_type": "topic" if topic_id else "none",
        "anchor_id": topic_id,
        "topic_id": topic_id,
        "anchor_title": topic_key.replace("-", " ").title() if topic_key else None,
        "episode_ids": [],
        "claim_ids": [],
        "page_ids": [page_id] if page_id else [],
        "source_paths": source_paths,
        "support_facts": _support_facts_from_mailbox_support(
            support_bundle=support_bundle,
            origin_shortcut_result=origin_shortcut_result,
        ),
        "bundle_mode": "topic-page-recent-origin" if topic_id else "unanchored",
        "generated_at": utc_now_iso(),
    }
    validate_pathfinder_bundle(bundle)
    return bundle


def _pathfinder_retrieval_result(
    *,
    query_text: str,
    status: str,
    stop_reason: str | None,
    source_refs: list[dict[str, Any]],
    mailbox_packet_refs: list[dict[str, Any]],
    support_bundle_shortcuts: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
    pathfinder_bundle: Mapping[str, Any] | None,
    lifecycle_records: list[dict[str, Any]],
    lifecycle_filter_mode: str,
    lifecycle_inactive_records_filtered: int,
    reason_codes: list[str],
) -> dict[str, Any]:
    active_reason_codes = list(reason_codes)
    if lifecycle_inactive_records_filtered:
        active_reason_codes.append("inactive_lifecycle_records_filtered")
    if lifecycle_filter_mode == "historical_including_inactive":
        active_reason_codes.append("historical_lifecycle_requested")
    result = {
        "schema_version": "pathfinder_retrieval_result.v1",
        "retrieval_result_id": uuid.uuid4().hex,
        "query_text": query_text,
        "status": status,
        "stop_reason": stop_reason,
        "source_refs": source_refs,
        "mailbox_packet_refs": mailbox_packet_refs,
        "support_bundle_shortcuts": dict(support_bundle_shortcuts),
        "origin_shortcut_result": dict(origin_shortcut_result) if isinstance(origin_shortcut_result, Mapping) else None,
        "pathfinder_bundle": dict(pathfinder_bundle) if isinstance(pathfinder_bundle, Mapping) else None,
        "lifecycle_filter_mode": lifecycle_filter_mode,
        "lifecycle_records": lifecycle_records,
        "lifecycle_inactive_records_filtered": lifecycle_inactive_records_filtered,
        "retrieval_authority": "mailbox_support_and_shortcut_consumption_only",
        "source_ref_authority": "required_forward_only",
        "bypassed_source_refs": False,
        "reason_codes": active_reason_codes,
        "created_at": utc_now_iso(),
    }
    validate_pathfinder_retrieval_result(result)
    return result


def build_pathfinder_retrieval_result(
    *,
    mailbox_support_result: Mapping[str, Any],
    workspace_root: Path | None = None,
    lifecycle_records: Sequence[Mapping[str, Any]] | None = None,
    include_historical_lifecycle: bool = False,
) -> dict[str, Any]:
    """Consume mailbox support without allowing source-less Pathfinder retrieval."""

    lifecycle_filter_mode = "historical_including_inactive" if include_historical_lifecycle else "active_only"
    selected_lifecycle_records, inactive_filtered = filter_lifecycle_records_for_retrieval(
        lifecycle_records,
        include_historical=include_historical_lifecycle,
    )
    source_refs = _source_refs(mailbox_support_result)
    mailbox_refs = _mailbox_packet_refs(mailbox_support_result)
    support_bundle = dict(mailbox_support_result.get("support_bundle") or {})
    shortcuts = _support_bundle_shortcuts(support_bundle) if support_bundle else {
        "canonical_note": None,
        "provenance_note": None,
        "source_paths": [],
        "pathfinder_source_paths": [],
    }
    query_text = str(mailbox_support_result.get("query_text") or support_bundle.get("query_text") or "").strip()
    if not query_text:
        query_text = str(mailbox_support_result.get("signal_id") or "unknown-query")

    try:
        validate_mailbox_support_result(mailbox_support_result)
    except Exception as exc:
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason=f"mailbox_support_result_invalid:{exc.__class__.__name__}",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["mailbox_support_result_invalid"],
        )

    if mailbox_support_result.get("status") != "completed":
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason=str(mailbox_support_result.get("stop_reason") or "mailbox_support_not_completed"),
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["mailbox_support_not_completed"],
        )

    if not support_bundle:
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason="support_bundle_missing",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["support_bundle_missing"],
        )

    try:
        validate_support_bundle(support_bundle)
    except Exception as exc:
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason=f"support_bundle_invalid:{exc.__class__.__name__}",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["support_bundle_invalid"],
        )

    if not _has_forwarded_source_ref(source_refs):
        return _pathfinder_retrieval_result(
            query_text=str(support_bundle["query_text"]),
            status="stopped",
            stop_reason="source_ref_missing",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["source_ref_missing"],
        )

    active_workspace = (workspace_root or OPENYGGDRASIL_ROOT).resolve()
    origin_result = mailbox_support_result.get("origin_shortcut_result")
    if isinstance(origin_result, Mapping):
        origin_result = dict(origin_result)
        validate_origin_shortcut_result(origin_result)
    else:
        origin_result = follow_origin_shortcut(support_bundle, workspace_root=active_workspace)
    if not bool(origin_result.get("exists")):
        return _pathfinder_retrieval_result(
            query_text=str(support_bundle["query_text"]),
            status="stopped",
            stop_reason="origin_shortcut_missing",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=origin_result,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["origin_shortcut_missing"],
        )

    bundle = _pathfinder_bundle_from_mailbox_support(
        support_bundle=support_bundle,
        origin_shortcut_result=origin_result,
    )
    return _pathfinder_retrieval_result(
        query_text=str(support_bundle["query_text"]),
        status="completed",
        stop_reason=None,
        source_refs=source_refs,
        mailbox_packet_refs=mailbox_refs,
        support_bundle_shortcuts=shortcuts,
        origin_shortcut_result=origin_result,
        pathfinder_bundle=bundle,
        lifecycle_records=selected_lifecycle_records,
        lifecycle_filter_mode=lifecycle_filter_mode,
        lifecycle_inactive_records_filtered=inactive_filtered,
        reason_codes=[
            "mailbox_support_consumed",
            "origin_shortcut_resolved",
            "source_refs_forwarded",
        ],
    )


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
