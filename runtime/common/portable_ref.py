from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
LOCAL_PATH_RE = re.compile(
    r"(?:\b[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|mnt|tmp|var|etc)/)",
    re.IGNORECASE,
)
ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|file://|/)")
PRIVATE_MATERIAL_TOKENS = (
    ".env",
    ".skill.md",
    "auth.json",
    "credential",
    "profile",
    "prompt",
    "state-db",
    "state_db",
    "state.db",
    "transcript",
    "transcript.txt",
    "transcripts/",
)


def looks_like_local_path(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(LOCAL_PATH_RE.search(text) or ABSOLUTE_PATH_RE.match(text))


def contains_private_material(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            contains_private_material(key) or contains_private_material(nested)
            for key, nested in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(contains_private_material(item) for item in value)
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower().replace("\\", "/")
    if looks_like_local_path(text):
        return True
    return any(token.replace("\\", "/") in lowered for token in PRIVATE_MATERIAL_TOKENS)


def validate_public_ref(
    value: object,
    *,
    field: str = "ref",
    unsafe_fragments: Sequence[str] = (),
) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if not SAFE_REF_RE.match(text):
        raise ValueError(f"{field} must be a safe portable ref")
    lowered = text.lower().replace("\\", "/")
    if looks_like_local_path(text) or any(
        token.replace("\\", "/") in lowered for token in PRIVATE_MATERIAL_TOKENS
    ):
        raise ValueError(f"{field} contains unsafe provider material")
    if any(str(fragment).lower().replace("\\", "/") in lowered for fragment in unsafe_fragments):
        raise ValueError(f"{field} contains unsafe provider material")
    return text


def reject_private_material(value: object, *, reason_prefix: str) -> None:
    if contains_private_material(value):
        raise ValueError(f"{reason_prefix}: private provider material is not allowed")
