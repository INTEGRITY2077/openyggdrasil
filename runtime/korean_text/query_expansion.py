from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from typing import Any


HANGUL_BASE = 0xAC00
HANGUL_END = 0xD7A3
JUNGSEONG_COUNT = 21
JONGSEONG_COUNT = 28
SYLLABLE_BLOCK = JUNGSEONG_COUNT * JONGSEONG_COUNT

CHOSEONGS = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]
JUNGSEONGS = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
]
JONGSEONGS = [
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]

CHOSEONG_SET = set(CHOSEONGS)
JUNGSEONG_SET = set(JUNGSEONGS)
JONGSEONG_SET = set(JONGSEONGS[1:])

JUNGSEONG_COMBINE = {
    ("ㅗ", "ㅏ"): "ㅘ",
    ("ㅗ", "ㅐ"): "ㅙ",
    ("ㅗ", "ㅣ"): "ㅚ",
    ("ㅜ", "ㅓ"): "ㅝ",
    ("ㅜ", "ㅔ"): "ㅞ",
    ("ㅜ", "ㅣ"): "ㅟ",
    ("ㅡ", "ㅣ"): "ㅢ",
}
JUNGSEONG_DECOMPOSE = {combined: parts for parts, combined in JUNGSEONG_COMBINE.items()}

JONGSEONG_COMBINE = {
    ("ㄱ", "ㅅ"): "ㄳ",
    ("ㄴ", "ㅈ"): "ㄵ",
    ("ㄴ", "ㅎ"): "ㄶ",
    ("ㄹ", "ㄱ"): "ㄺ",
    ("ㄹ", "ㅁ"): "ㄻ",
    ("ㄹ", "ㅂ"): "ㄼ",
    ("ㄹ", "ㅅ"): "ㄽ",
    ("ㄹ", "ㅌ"): "ㄾ",
    ("ㄹ", "ㅍ"): "ㄿ",
    ("ㄹ", "ㅎ"): "ㅀ",
    ("ㅂ", "ㅅ"): "ㅄ",
}
JONGSEONG_DECOMPOSE = {combined: parts for parts, combined in JONGSEONG_COMBINE.items()}

QWERTY_TO_JAMO = {
    "r": "ㄱ", "R": "ㄲ", "s": "ㄴ", "e": "ㄷ", "E": "ㄸ",
    "f": "ㄹ", "a": "ㅁ", "q": "ㅂ", "Q": "ㅃ", "t": "ㅅ",
    "T": "ㅆ", "d": "ㅇ", "w": "ㅈ", "W": "ㅉ", "c": "ㅊ",
    "z": "ㅋ", "x": "ㅌ", "v": "ㅍ", "g": "ㅎ",
    "k": "ㅏ", "o": "ㅐ", "i": "ㅑ", "O": "ㅒ", "j": "ㅓ",
    "p": "ㅔ", "u": "ㅕ", "P": "ㅖ", "h": "ㅗ", "y": "ㅛ",
    "n": "ㅜ", "b": "ㅠ", "m": "ㅡ", "l": "ㅣ",
}
JAMO_TO_QWERTY = {jamo: key.lower() for key, jamo in QWERTY_TO_JAMO.items() if key.islower()}
JAMO_TO_QWERTY.update({"ㄲ": "R", "ㄸ": "E", "ㅃ": "Q", "ㅆ": "T", "ㅉ": "W", "ㅒ": "O", "ㅖ": "P"})

HANGUL_SPAN_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]+")
ASCII_SPAN_RE = re.compile(r"[A-Za-z]+")


def _is_complete_hangul(char: str) -> bool:
    return len(char) == 1 and HANGUL_BASE <= ord(char) <= HANGUL_END


def _decompose_syllable(char: str) -> tuple[str, str, str] | None:
    if not _is_complete_hangul(char):
        return None
    offset = ord(char) - HANGUL_BASE
    choseong = offset // SYLLABLE_BLOCK
    jungseong = (offset % SYLLABLE_BLOCK) // JONGSEONG_COUNT
    jongseong = offset % JONGSEONG_COUNT
    return CHOSEONGS[choseong], JUNGSEONGS[jungseong], JONGSEONGS[jongseong]


def _compose_syllable(choseong: str, jungseong: str, jongseong: str = "") -> str:
    return chr(
        HANGUL_BASE
        + CHOSEONGS.index(choseong) * SYLLABLE_BLOCK
        + JUNGSEONGS.index(jungseong) * JONGSEONG_COUNT
        + JONGSEONGS.index(jongseong)
    )


def _decompose_jungseong(jungseong: str) -> tuple[str, ...]:
    return JUNGSEONG_DECOMPOSE.get(jungseong, (jungseong,))


def _decompose_jongseong(jongseong: str) -> tuple[str, ...]:
    if not jongseong:
        return ()
    return JONGSEONG_DECOMPOSE.get(jongseong, (jongseong,))


def _is_vowel(jamo: str) -> bool:
    return jamo in JUNGSEONG_SET


def _is_consonant(jamo: str) -> bool:
    return jamo in CHOSEONG_SET or jamo in JONGSEONG_SET


def _combine_vowel(first: str, second: str) -> str | None:
    return JUNGSEONG_COMBINE.get((first, second))


def _combine_final(first: str, second: str) -> str | None:
    return JONGSEONG_COMBINE.get((first, second))


def get_choseong(text: str) -> str:
    """Return initial-consonant text for complete Hangul syllables.

    This is a deterministic string helper. It is not morphology, grammar
    correction, or semantic normalization.
    """
    result: list[str] = []
    for char in unicodedata.normalize("NFC", text):
        parts = _decompose_syllable(char)
        if parts:
            result.append(parts[0])
        elif char in CHOSEONG_SET:
            result.append(char)
    return "".join(result)


def decompose_to_jamo(text: str) -> str:
    """Decompose complete Hangul syllables into compatibility jamo."""
    result: list[str] = []
    for char in unicodedata.normalize("NFC", text):
        parts = _decompose_syllable(char)
        if parts is None:
            result.append(char)
            continue
        choseong, jungseong, jongseong = parts
        result.append(choseong)
        result.extend(_decompose_jungseong(jungseong))
        result.extend(_decompose_jongseong(jongseong))
    return "".join(result)


def hangul_to_qwerty(text: str) -> str:
    """Convert Hangul syllables/jamo to two-beolsik QWERTY keystrokes."""
    result: list[str] = []
    for char in unicodedata.normalize("NFC", text):
        parts = _decompose_syllable(char)
        if parts is None:
            result.append(JAMO_TO_QWERTY.get(char, char))
            continue
        choseong, jungseong, jongseong = parts
        result.append(JAMO_TO_QWERTY.get(choseong, choseong))
        for jamo in _decompose_jungseong(jungseong):
            result.append(JAMO_TO_QWERTY.get(jamo, jamo))
        for jamo in _decompose_jongseong(jongseong):
            result.append(JAMO_TO_QWERTY.get(jamo, jamo))
    return "".join(result)


def _qwerty_to_jamo(text: str) -> list[str]:
    return [QWERTY_TO_JAMO.get(char, char) for char in text]


def qwerty_to_hangul(text: str) -> str:
    """Best-effort two-beolsik QWERTY to Hangul conversion for search expansion.

    The converter is intentionally conservative. It is suitable for recall/query
    expansion, not for canonical text rewriting.
    """
    jamo = _qwerty_to_jamo(text)
    result: list[str] = []
    i = 0
    while i < len(jamo):
        current = jamo[i]
        if not _is_consonant(current) or i + 1 >= len(jamo) or not _is_vowel(jamo[i + 1]):
            result.append(current)
            i += 1
            continue

        choseong = current
        jungseong = jamo[i + 1]
        i += 2

        if i < len(jamo) and _is_vowel(jamo[i]):
            combined = _combine_vowel(jungseong, jamo[i])
            if combined is not None:
                jungseong = combined
                i += 1

        jongseong = ""
        if i < len(jamo) and _is_consonant(jamo[i]):
            first_final = jamo[i]
            next_is_vowel = i + 1 < len(jamo) and _is_vowel(jamo[i + 1])
            if not next_is_vowel and first_final in JONGSEONG_SET:
                jongseong = first_final
                i += 1
                if i < len(jamo) and _is_consonant(jamo[i]):
                    after_cluster_is_vowel = i + 1 < len(jamo) and _is_vowel(jamo[i + 1])
                    combined_final = _combine_final(jongseong, jamo[i])
                    if combined_final is not None and not after_cluster_is_vowel:
                        jongseong = combined_final
                        i += 1

        result.append(_compose_syllable(choseong, jungseong, jongseong))
    return "".join(result)


def _add_unique(target: OrderedDict[str, None], value: str, *, max_len: int = 80) -> None:
    clean = " ".join(str(value or "").strip().split())
    if not clean or len(clean) > max_len:
        return
    target.setdefault(clean, None)


def _contains_complete_hangul(text: str) -> bool:
    return any(_is_complete_hangul(char) for char in text)


def _is_choseong_query(text: str) -> bool:
    return bool(text) and all(char in CHOSEONG_SET for char in text)


def query_expansion_tokens(text: str, *, max_tokens: int = 32) -> list[str]:
    """Return secondary search tokens for Hangul recall.

    Tokens are prefixed so they do not collide with natural words. Kiwi or the
    existing primary tokenizer should remain the main retrieval signal.
    """
    tokens: OrderedDict[str, None] = OrderedDict()
    normalized = unicodedata.normalize("NFC", str(text or ""))

    for match in HANGUL_SPAN_RE.finditer(normalized):
        span = match.group(0)
        if len(span) > 40:
            continue
        if _contains_complete_hangul(span):
            _add_unique(tokens, f"ko_cho:{get_choseong(span)}")
            _add_unique(tokens, f"ko_jamo:{decompose_to_jamo(span)}")
            _add_unique(tokens, f"ko_qwerty:{hangul_to_qwerty(span).lower()}")
        elif _is_choseong_query(span):
            _add_unique(tokens, f"ko_cho:{span}")
        if len(tokens) >= max_tokens:
            return list(tokens.keys())[:max_tokens]

    for match in ASCII_SPAN_RE.finditer(normalized):
        span = match.group(0)
        if len(span) > 60:
            continue
        converted = qwerty_to_hangul(span)
        if converted == span or not _contains_complete_hangul(converted):
            continue
        _add_unique(tokens, f"ko_qwerty:{span.lower()}")
        _add_unique(tokens, f"ko_hangul:{converted}")
        _add_unique(tokens, f"ko_cho:{get_choseong(converted)}")
        _add_unique(tokens, f"ko_jamo:{decompose_to_jamo(converted)}")
        if len(tokens) >= max_tokens:
            return list(tokens.keys())[:max_tokens]

    return list(tokens.keys())[:max_tokens]


def expand_korean_query(query: str, *, max_input_chars: int = 200, max_expansions: int = 16) -> dict[str, Any]:
    """Build a bounded query-expansion contract for Korean recall.

    This function never rewrites canonical memory text. It only returns optional
    secondary search terms.
    """
    original = str(query or "")
    if len(original) > max_input_chars:
        return {
            "status": "typed_unavailable",
            "original": original,
            "expansions": [],
            "tokens": [],
            "typed_unavailable": {
                "schema_version": "typed_unavailable.v1",
                "reason_code": "korean_query_too_long",
                "blocked_stage": "korean_query_expansion",
                "missing_or_rejected_refs": [
                    {
                        "ref": "query",
                        "reason_code": "length_exceeds_limit",
                        "rejection_kind": "safety_limit",
                    }
                ],
            },
            "hard_nonclaims": _hard_nonclaims(),
        }

    expansions: OrderedDict[str, None] = OrderedDict()
    normalized = unicodedata.normalize("NFC", original)
    _add_unique(expansions, normalized)
    tokens = query_expansion_tokens(normalized, max_tokens=max_expansions)
    for token in tokens:
        if ":" in token:
            _add_unique(expansions, token.split(":", 1)[1])

    return {
        "status": "ready",
        "original": original,
        "expansions": list(expansions.keys())[:max_expansions],
        "tokens": tokens[:max_expansions],
        "hard_nonclaims": _hard_nonclaims(),
    }


def _hard_nonclaims() -> dict[str, bool]:
    return {
        "grammar_checker": False,
        "kiwi_replacement": False,
        "canonical_text_rewriter": False,
        "semantic_quality_proof": False,
        "es_hangul_code_copied": False,
    }


def build_korean_query_expansion_metadata(query: str, *, max_expansions: int = 16) -> dict[str, Any]:
    """Build provider/MF-visible metadata for secondary Hangul recall signals."""
    expanded = expand_korean_query(query, max_expansions=max_expansions)
    metadata = {
        "schema_version": "korean_query_expansion.v1",
        "original_query": str(query or ""),
        "expansion_status": expanded["status"],
        "expansion_tokens": expanded.get("tokens", []),
        "expansions": expanded.get("expansions", []),
        "used_as_secondary_signal": expanded["status"] == "ready" and bool(expanded.get("tokens")),
        "primary_language_analyzer": "kiwipiepy_or_existing_tokenizer",
        "hard_nonclaims": {
            "not_grammar_checker": True,
            "not_kiwi_replacement": True,
            "not_semantic_quality_proof": True,
            "not_canonical_text_rewriter": True,
            "not_es_hangul_code_copied": True,
        },
    }
    if expanded.get("typed_unavailable"):
        metadata["typed_unavailable"] = expanded["typed_unavailable"]
    return metadata
