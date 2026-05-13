from __future__ import annotations

import re
import uuid
from typing import Any, Mapping

from runtime.common.portable_ref import looks_like_local_path
from harness_common import utc_now_iso


LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2}$")
SAFE_REF_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://openyggdrasil/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=-]+$")


def normalize_language_code(language_code: str) -> str:
    code = str(language_code or "").strip().lower()
    if not LANGUAGE_CODE_PATTERN.fullmatch(code):
        raise ValueError("language_code must be an ISO 639-1 two-letter code")
    return code


def require_safe_ref(value: str, *, field: str = "source_ref") -> str:
    ref = str(value or "").strip()
    if not ref:
        raise ValueError(f"{field} is required")
    if looks_like_local_path(ref):
        raise ValueError(f"{field} must not contain a local filesystem path")
    if not SAFE_REF_PATTERN.fullmatch(ref):
        raise ValueError(f"{field} must be a safe openyggdrasil typed ref")
    return ref


def build_wiki_capture_signal(
    *,
    provider_id: str,
    provider_session_id: str,
    language_code: str,
    source_ref: str,
    source_turn_ref: str,
    topic_hint: str,
    emitted_at: str | None = None,
) -> dict[str, Any]:
    """Build the bounded wiki-capture signal used by the E12D safety gate."""

    source = require_safe_ref(source_ref)
    turn_ref = require_safe_ref(source_turn_ref, field="source_turn_ref")
    topic = str(topic_hint or "").strip()
    if not topic:
        raise ValueError("topic_hint is required")
    return {
        "schema_version": "wiki_capture_signal.v1",
        "signal_id": uuid.uuid4().hex,
        "provider_id": str(provider_id or "").strip(),
        "provider_session_id": str(provider_session_id or "").strip(),
        "language_code": normalize_language_code(language_code),
        "source_trace": {
            "source_ref": source,
            "source_turn_ref": turn_ref,
            "topic_hint": topic,
        },
        "raw_transcript_included": False,
        "semantic_extraction_solved_claimed": False,
        "emitted_at": emitted_at or utc_now_iso(),
    }


def validate_wiki_capture_signal(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "wiki_capture_signal.v1":
        raise ValueError("Invalid wiki_capture_signal schema_version")
    if not str(payload.get("signal_id") or "").strip():
        raise ValueError("wiki_capture_signal requires signal_id")
    if not str(payload.get("provider_id") or "").strip():
        raise ValueError("wiki_capture_signal requires provider_id")
    if not str(payload.get("provider_session_id") or "").strip():
        raise ValueError("wiki_capture_signal requires provider_session_id")
    normalize_language_code(str(payload.get("language_code") or ""))
    source_trace = payload.get("source_trace")
    if not isinstance(source_trace, Mapping):
        raise ValueError("wiki_capture_signal requires source_trace")
    require_safe_ref(str(source_trace.get("source_ref") or ""))
    require_safe_ref(str(source_trace.get("source_turn_ref") or ""), field="source_turn_ref")
    if not str(source_trace.get("topic_hint") or "").strip():
        raise ValueError("wiki_capture_signal requires topic_hint")
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("wiki_capture_signal must not include raw transcript")
    if payload.get("semantic_extraction_solved_claimed") is not False:
        raise ValueError("wiki_capture_signal must not claim semantic extraction solved")
