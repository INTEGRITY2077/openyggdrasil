from __future__ import annotations

from pathlib import Path
from typing import Any

from .hermes_session_json import resolve_hermes_session_json_source_ref


def resolve_source_ref(
    *,
    source_ref: str,
    range_hint: dict[str, Any] | None = None,
    anchor_hash: str = "",
    resolver_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Provider-neutral source_ref registry.

    OP1/OP2 core는 provider별 저장소 구조를 알지 않는다. Provider별 원본 접근은
    이 registry 뒤의 adapter만 수행한다.
    """
    range_hint = range_hint or {}
    resolver_options = resolver_options or {}

    if source_ref.startswith("hermes-session-json://"):
        sessions_dir = resolver_options.get("sessions_dir")
        if not sessions_dir:
            return {
                "status": "unavailable",
                "reason": "resolver_option_missing:sessions_dir",
                "source_ref": source_ref,
                "resolver_status": "unavailable",
                "redaction_status": "not_applicable",
            }
        return resolve_hermes_session_json_source_ref(
            source_ref=source_ref,
            message_index_range={"start": int(range_hint.get("start", 0)), "end": int(range_hint.get("end", 0))},
            sessions_dir=Path(sessions_dir),
            anchor_hash=anchor_hash,
        )

    return {
        "status": "unavailable",
        "reason": "unsupported_source_ref_scheme",
        "source_ref": source_ref,
        "resolver_status": "unavailable",
        "redaction_status": "not_applicable",
    }
