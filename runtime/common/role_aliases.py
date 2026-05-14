from __future__ import annotations

import re
from typing import Any


CANONICAL_PROVIDER_ROLE = "provider"
CANONICAL_MEMORY_SAVER_ROLE = "memory_saver"
CANONICAL_MEMORY_FINDER_ROLE = "memory_finder"

LEGACY_ACTIVE_OPERATOR_PAIR = ("MS1", "MF1")
LEGACY_OPERATOR_TMUX_SESSION_PATTERN = r"^(oy-op\d+|ygg-op\d+|ygg-ms\d+|ygg-mf\d+)$"

WORKER_ROLE_MAILBOX_NAMES = {
    CANONICAL_MEMORY_SAVER_ROLE: "MS1",
    CANONICAL_MEMORY_FINDER_ROLE: "MF1",
}
WORKER_ROLE_SHORT_LABELS = {
    CANONICAL_MEMORY_SAVER_ROLE: "MS1",
    CANONICAL_MEMORY_FINDER_ROLE: "MF1",
}
WORKER_ROLE_SURFACE_LABELS = {
    CANONICAL_MEMORY_SAVER_ROLE: "MS1 Memory Saver",
    CANONICAL_MEMORY_FINDER_ROLE: "MF1 Memory Finder",
}
WORKER_ROLE_ALIASES = {
    CANONICAL_MEMORY_SAVER_ROLE: frozenset(
        {"ms", "ms1", "memory_saver", "memory-saver", "saver", "producer"}
    ),
    CANONICAL_MEMORY_FINDER_ROLE: frozenset(
        {"mf", "mf1", "memory_finder", "memory-finder", "finder", "consumer"}
    ),
}

LIVE_GROUP_ROLE_ALIASES = {
    "provider": ("provider", "pro1", "ygg-pro1", "hermes"),
    "ms1": ("ms1", "memory_saver_1", "producer", "ygg-ms1"),
    "mf1": ("mf1", "memory_finder_1", "consumer", "ygg-mf1"),
}
LIVE_GROUP_ROLE_DISPLAY_NAMES = {
    "provider": "Provider Lane",
    "ms1": "MS1 Memory Saver",
    "mf1": "MF1 Memory Finder",
}
LIVE_GROUP_ROLE_COMMAND_TARGETS = {
    "provider": "ygg pro1",
    "ms1": "ygg ms1",
    "mf1": "ygg mf1",
}
LIVE_GROUP_LEGACY_ALIAS_REPLACEMENTS = {
    "ms1": (),
    "mf1": (),
}

ROW_8_LIVE_VERIFICATION_LABEL = "row_8_live_verification"
ROW_8_EXECUTOR_PENDING_STATUS = "EXECUTOR_BOUNDARY_NOT_LIVE_UNTIL_ROW_8_LIVE_VERIFICATION"
LEGACY_WORKER4_PASS_LABEL = "Worker 4 PASS"
LEGACY_WORKER4_VERIFICATION_EVIDENCE_ID = "worker4-verification-pass-001"
LEGACY_WORKER4_VERIFICATION_EVIDENCE_KIND = "worker4_verification"
LEGACY_WORKER4_VERIFICATION_REF = (
    "worker4-verification-ref://openyggdrasil/producer-first-poc/worker4/pass-001"
)
LEGACY_MEMORY_FINDER_SUPPORT_METADATA_FIELD = "mf1_support_metadata"


def _alias_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def normalize_worker_role(value: Any) -> str:
    key = _alias_key(value)
    for role, aliases in WORKER_ROLE_ALIASES.items():
        if key in {alias.replace("-", "_") for alias in aliases}:
            return role
    return key or "unknown"


def legacy_mailbox_name_for_role(role: Any) -> str:
    normalized = normalize_worker_role(role)
    try:
        return WORKER_ROLE_MAILBOX_NAMES[normalized]
    except KeyError as exc:
        raise ValueError("unsupported_worker_role") from exc


def legacy_mailbox_name_for_mode(mode: Any) -> str:
    text = str(mode or "").strip().lower()
    if text == "produce":
        return legacy_mailbox_name_for_role(CANONICAL_MEMORY_SAVER_ROLE)
    if text == "consume":
        return legacy_mailbox_name_for_role(CANONICAL_MEMORY_FINDER_ROLE)
    raise ValueError("unsupported_worker_mode")


def worker_short_label_for_mode(mode: Any) -> str:
    text = str(mode or "").strip().lower()
    if text == "produce":
        return WORKER_ROLE_SHORT_LABELS[CANONICAL_MEMORY_SAVER_ROLE]
    if text == "consume":
        return WORKER_ROLE_SHORT_LABELS[CANONICAL_MEMORY_FINDER_ROLE]
    raise ValueError("unsupported_worker_mode")


def worker_surface_label(role: Any) -> str:
    return WORKER_ROLE_SURFACE_LABELS.get(normalize_worker_role(role), "Unknown Worker")


def scrub_live_group_legacy_alias(role: str, value: str) -> str:
    safe_value = str(value)
    for old, new in LIVE_GROUP_LEGACY_ALIAS_REPLACEMENTS.get(role, ()):
        safe_value = re.sub(re.escape(old), new, safe_value, flags=re.IGNORECASE)
    return safe_value


__all__ = [
    "CANONICAL_MEMORY_FINDER_ROLE",
    "CANONICAL_MEMORY_SAVER_ROLE",
    "CANONICAL_PROVIDER_ROLE",
    "LEGACY_ACTIVE_OPERATOR_PAIR",
    "LEGACY_OPERATOR_TMUX_SESSION_PATTERN",
    "LEGACY_WORKER4_PASS_LABEL",
    "LEGACY_WORKER4_VERIFICATION_EVIDENCE_ID",
    "LEGACY_WORKER4_VERIFICATION_EVIDENCE_KIND",
    "LEGACY_WORKER4_VERIFICATION_REF",
    "LEGACY_MEMORY_FINDER_SUPPORT_METADATA_FIELD",
    "LIVE_GROUP_ROLE_ALIASES",
    "LIVE_GROUP_ROLE_COMMAND_TARGETS",
    "LIVE_GROUP_ROLE_DISPLAY_NAMES",
    "ROW_8_EXECUTOR_PENDING_STATUS",
    "ROW_8_LIVE_VERIFICATION_LABEL",
    "WORKER_ROLE_MAILBOX_NAMES",
    "WORKER_ROLE_SHORT_LABELS",
    "WORKER_ROLE_SURFACE_LABELS",
    "legacy_mailbox_name_for_mode",
    "legacy_mailbox_name_for_role",
    "normalize_worker_role",
    "scrub_live_group_legacy_alias",
    "worker_short_label_for_mode",
    "worker_surface_label",
]
