from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


LOCAL_DOCS_SCHEME = "local-docs"


def _canonical_local_docs_anchor_hash(source_segments: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps(list(source_segments), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _typed_unavailable(source_ref: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "source_ref": source_ref,
        "resolver_status": "unavailable",
        "redaction_status": "not_applicable",
        **extra,
    }


def _parse_local_docs_source_ref(source_ref: str) -> str | None:
    prefix = f"{LOCAL_DOCS_SCHEME}://"
    if not source_ref.startswith(prefix):
        return None
    key = source_ref[len(prefix) :].strip()
    return key or None


def _parse_evidence_pointer(pointer: str) -> tuple[str, int, int] | None:
    match = re.fullmatch(r"(.+):([0-9]+)(?:-([0-9]+))?", pointer.strip())
    if not match:
        return None
    start = int(match.group(2))
    end = int(match.group(3) or match.group(2))
    if start < 1 or end < start:
        return None
    return match.group(1), start, end


def _safe_relative(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _segment_from_pointer(pointer: str, *, docs_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    parsed = _parse_evidence_pointer(pointer)
    if not parsed:
        return None, "evidence_pointer_malformed"
    raw_path, start, end = parsed
    candidate = Path(raw_path)
    path = candidate if candidate.is_absolute() else docs_root / candidate
    relative = _safe_relative(path, docs_root)
    if relative is None:
        return None, "source_path_outside_docs_root"
    if not path.exists() or not path.is_file():
        return None, "source_path_not_found"
    lines = path.read_text(encoding="utf-8").splitlines()
    if end > len(lines):
        return None, "source_line_range_out_of_bounds"
    return {
        "path": relative,
        "start": start,
        "end": end,
        "lines": lines[start - 1 : end],
    }, None


def build_local_docs_source_segments(*, docs_root: str | Path, evidence: Sequence[str]) -> list[dict[str, Any]]:
    root = Path(docs_root)
    segments: list[dict[str, Any]] = []
    for pointer in evidence:
        segment, reason = _segment_from_pointer(str(pointer), docs_root=root)
        if reason:
            raise ValueError(reason)
        if segment is not None:
            segments.append(segment)
    return segments


def resolve_local_docs_source_ref(
    *,
    source_ref: str,
    range_hint: dict[str, Any] | None = None,
    anchor_hash: str = "",
    resolver_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    range_hint = range_hint or {}
    resolver_options = resolver_options or {}
    key = _parse_local_docs_source_ref(source_ref)
    if key is None:
        return {
            "status": "reject",
            "reason": "unsupported_source_ref",
            "source_ref": source_ref,
            "resolver_status": "reject",
            "redaction_status": "not_applicable",
        }

    docs_roots = resolver_options.get("docs_roots")
    if not isinstance(docs_roots, Mapping) or key not in docs_roots:
        return _typed_unavailable(source_ref, "resolver_option_missing:docs_roots")

    evidence = resolver_options.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)) or not evidence:
        return _typed_unavailable(source_ref, "resolver_option_missing:evidence")

    docs_root = Path(str(docs_roots[key]))
    if not docs_root.exists() or not docs_root.is_dir():
        return _typed_unavailable(source_ref, "docs_root_not_found")

    segments: list[dict[str, Any]] = []
    for pointer in evidence:
        segment, reason = _segment_from_pointer(str(pointer), docs_root=docs_root)
        if reason:
            return _typed_unavailable(source_ref, reason, evidence_pointer=str(pointer))
        if segment is not None:
            segments.append(segment)
    if not segments:
        return _typed_unavailable(source_ref, "source_segments_empty")

    computed_anchor_hash = _canonical_local_docs_anchor_hash(segments)
    if anchor_hash and computed_anchor_hash != anchor_hash:
        return _typed_unavailable(
            source_ref,
            "anchor_hash_mismatch",
            anchor_hash=anchor_hash,
            computed_anchor_hash=computed_anchor_hash,
        )

    source_line_range = range_hint.get("source_line_range")
    if not isinstance(source_line_range, Mapping):
        first = segments[0]
        last = segments[-1]
        source_line_range = {
            "start": first["start"],
            "end": last["end"],
        }

    origin_locator = ";".join(f"{source_ref}/{row['path']}:{row['start']}-{row['end']}" for row in segments)
    return {
        "status": "resolved",
        "source_ref_scheme": LOCAL_DOCS_SCHEME,
        "source_ref": source_ref,
        "source_key": key,
        "source_line_range": dict(source_line_range),
        "message_index_range": {
            "start": range_hint.get("start"),
            "end": range_hint.get("end"),
        },
        "origin_locator": origin_locator,
        "commit_watermark": f"local-docs:{key}:{computed_anchor_hash[:12]}",
        "anchor_hash": anchor_hash or computed_anchor_hash,
        "computed_anchor_hash": computed_anchor_hash,
        "source_segments": segments,
        "resolver_status": "resolved",
        "redaction_status": "pointer_only",
        "hard_nonclaims": [
            "local_docs_resolver_uses_bounded_evidence_pointers_only",
            "resolved_lines_are_source_snippets_not_raw_provider_transcript",
        ],
    }


def register_local_docs_resolver() -> None:
    from .registry import register_source_ref_resolver

    register_source_ref_resolver(LOCAL_DOCS_SCHEME, resolve_local_docs_source_ref)


__all__ = [
    "LOCAL_DOCS_SCHEME",
    "_canonical_local_docs_anchor_hash",
    "build_local_docs_source_segments",
    "register_local_docs_resolver",
    "resolve_local_docs_source_ref",
]
