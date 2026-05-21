from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class IntentMarkerFamily:
    name: str
    markers: tuple[str, ...]

    def matches(self, text: str) -> bool:
        normalized = normalize_intent_text(text)
        return any(marker in normalized for marker in self.markers)


def normalize_intent_text(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _family(name: str, markers: Iterable[str]) -> IntentMarkerFamily:
    normalized = tuple(sorted({normalize_intent_text(marker) for marker in markers if normalize_intent_text(marker)}))
    return IntentMarkerFamily(name=name, markers=normalized)


# These are intent families, not topic taxonomies. They describe the shape of a
# Provider turn that may need source-backed recall or delayed correction across
# any domain: software, biology, memory-system design, or another future topic.
SOURCE_BACKED_MEMORY_NEED = _family(
    "source_backed_memory_need",
    (
        "근거",
        "출처",
        "위키",
        "위키 근거",
        "문서 근거",
        "저장된",
        "저장본",
        "저장 근거",
        "이전 기준",
        "전에 정리한",
        "기준",
        "확인해줘",
        "검증해줘",
        "찾아줘",
        "없으면 없다고",
        "부족하면",
        "unsupported",
        "support",
        "source-backed",
        "source backed",
        "stored evidence",
        "saved evidence",
        "wiki-backed",
        "previous decision",
        "earlier session",
        "verify",
        "evidence",
    ),
)

PROGRESSIVE_FOLLOWUP_INTENT = _family(
    "progressive_followup_intent",
    (
        "방금",
        "아까",
        "나중에",
        "뒤에서",
        "다시",
        "이어지면",
        "계속",
        "달라지면",
        "바뀌면",
        "다르면",
        "다시 물어",
        "정정해줘",
        "확인해줘",
        "check later",
        "correct later",
        "follow up",
        "if it differs",
        "later",
        "previous basis",
        "same basis",
    ),
)

HERMES_NATIVE_MEMORY_MAINTENANCE = _family(
    "hermes_native_memory_maintenance",
    (
        "review the conversation above and update the skill library",
        "target shape of the library: class-level skills",
        "most sessions produce at least one skill update",
        "self-improvement review",
        "user profile updated",
    ),
)

PROVIDER_INTENT_FAMILIES = (
    SOURCE_BACKED_MEMORY_NEED,
    PROGRESSIVE_FOLLOWUP_INTENT,
    HERMES_NATIVE_MEMORY_MAINTENANCE,
)


def has_source_backed_memory_need(text: str) -> bool:
    return SOURCE_BACKED_MEMORY_NEED.matches(text)


def has_progressive_followup_intent(text: str) -> bool:
    return PROGRESSIVE_FOLLOWUP_INTENT.matches(text)


def has_progressive_source_backed_recall_intent(text: str) -> bool:
    return has_progressive_followup_intent(text) and has_source_backed_memory_need(text)


def is_hermes_native_memory_maintenance_prompt(text: str) -> bool:
    return HERMES_NATIVE_MEMORY_MAINTENANCE.matches(text)
