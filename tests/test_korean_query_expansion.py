from __future__ import annotations

import operator  # noqa: F401 - stdlib pre-import prevents runtime/operator shadowing in this repo layout.
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from korean_text.query_expansion import (
    build_korean_query_expansion_metadata,
    decompose_to_jamo,
    expand_korean_query,
    get_choseong,
    hangul_to_qwerty,
    query_expansion_tokens,
    qwerty_to_hangul,
)
from ptc.primitives import search_vault_by_keyword
from runtime.operator.consumer import run_consumer


def test_basic_hangul_string_helpers_are_deterministic() -> None:
    assert get_choseong("한글 검색") == "ㅎㄱㄱㅅ"
    assert decompose_to_jamo("한글") == "ㅎㅏㄴㄱㅡㄹ"
    assert hangul_to_qwerty("한글") == "gksrmf"
    assert qwerty_to_hangul("gksrmf") == "한글"
    assert qwerty_to_hangul("rkskek") == "가나다"


def test_query_expansion_contract_preserves_nonclaims() -> None:
    expanded = expand_korean_query("gksrmf")

    assert expanded["status"] == "ready"
    assert "한글" in expanded["expansions"]
    assert "ko_cho:ㅎㄱ" in expanded["tokens"]
    assert expanded["hard_nonclaims"]["grammar_checker"] is False
    assert expanded["hard_nonclaims"]["kiwi_replacement"] is False
    assert expanded["hard_nonclaims"]["canonical_text_rewriter"] is False
    assert expanded["hard_nonclaims"]["semantic_quality_proof"] is False
    assert expanded["hard_nonclaims"]["es_hangul_code_copied"] is False

    metadata = build_korean_query_expansion_metadata("gksrmf")
    assert metadata["schema_version"] == "korean_query_expansion.v1"
    assert metadata["original_query"] == "gksrmf"
    assert metadata["expansion_status"] == "ready"
    assert metadata["used_as_secondary_signal"] is True
    assert metadata["hard_nonclaims"]["not_grammar_checker"] is True
    assert metadata["hard_nonclaims"]["not_kiwi_replacement"] is True
    assert metadata["hard_nonclaims"]["not_semantic_quality_proof"] is True


def test_query_expansion_typed_unavailable_for_overlong_input() -> None:
    expanded = expand_korean_query("한" * 201)

    assert expanded["status"] == "typed_unavailable"
    assert expanded["typed_unavailable"]["reason_code"] == "korean_query_too_long"
    assert expanded["tokens"] == []


def test_secondary_tokens_support_choseong_and_qwerty_recall() -> None:
    tokens_for_doc = query_expansion_tokens("한글 검색")
    tokens_for_choseong_query = query_expansion_tokens("ㅎㄱ")
    tokens_for_qwerty_query = query_expansion_tokens("gksrmf")

    assert "ko_cho:ㅎㄱ" in tokens_for_doc
    assert "ko_cho:ㅎㄱ" in tokens_for_choseong_query
    assert "ko_qwerty:gksrmf" in tokens_for_doc
    assert "ko_qwerty:gksrmf" in tokens_for_qwerty_query


def test_ptc_keyword_search_keeps_hangul_expansion_secondary() -> None:
    nodes = [
        {
            "node_id": "N-hangul",
            "spo": {
                "subject": "한글 검색 경로",
                "predicate": "supports",
                "object": "초성 검색과 QWERTY 오타 검색",
                "source_sentence": "한글 검색은 보조 확장 토큰으로만 처리한다.",
            },
        },
        {
            "node_id": "N-other",
            "spo": {
                "subject": "English route",
                "predicate": "supports",
                "object": "unrelated lookup",
                "source_sentence": "No Korean text here.",
            },
        },
    ]

    choseong_results = search_vault_by_keyword(nodes, "ㅎㄱ")
    qwerty_results = search_vault_by_keyword(nodes, "gksrmf")

    assert choseong_results[0]["node_id"] == "N-hangul"
    assert qwerty_results[0]["node_id"] == "N-hangul"


def test_op2_consumer_exposes_korean_query_expansion_metadata(tmp_path: Path) -> None:
    vault_node = tmp_path / "concepts" / "N-hangul.md"
    vault_node.parent.mkdir(parents=True)
    vault_node.write_text(
        """---
node_id: N-hangul
title: 한글 검색 경로
type: concept
status: ACTIVE
---
# 한글 검색 경로

- **Subject:** 한글 검색 경로
- **Predicate:** supports
- **Object:** 초성 검색과 QWERTY 오타 검색
> 한글 검색은 보조 확장 토큰으로만 처리한다.
""",
        encoding="utf-8",
    )
    mailbox = tmp_path / "mailbox"
    mailbox.mkdir()
    (mailbox / "queries.jsonl").write_text(
        '{"mail_id": "ask-hangul", "payload": {"query_text": "ㅎㄱ"}}\n',
        encoding="utf-8",
    )

    run_consumer(mailbox, tmp_path)

    receipt = (mailbox / "query_receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    bundle = __import__("json").loads(receipt)["bundle"]
    metadata = bundle["korean_query_expansion"]

    assert bundle["support_facts"][0]["node_id"] == "N-hangul"
    assert metadata["schema_version"] == "korean_query_expansion.v1"
    assert metadata["original_query"] == "ㅎㄱ"
    assert metadata["expansion_status"] == "ready"
    assert "ko_cho:ㅎㄱ" in metadata["expansion_tokens"]
    assert metadata["used_as_secondary_signal"] is True
    assert metadata["hard_nonclaims"]["not_grammar_checker"] is True
    assert metadata["hard_nonclaims"]["not_kiwi_replacement"] is True
    assert metadata["hard_nonclaims"]["not_semantic_quality_proof"] is True
