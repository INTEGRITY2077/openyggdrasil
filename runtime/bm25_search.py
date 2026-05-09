"""
BM25 Search — rank-bm25 기반 Vault 검색 CLI.

consumer.py → subprocess.run([sys.executable, "bm25_search.py", ...]) → JSON stdout

의존성: rank-bm25 (numpy) — 순수 Python, 벡터 임베딩 불필요.
설치: pip install rank-bm25

Usage:
    python3 runtime/bm25_search.py --vault /path/to/vault --query "검색어" [--top-k 20]
"""

from __future__ import annotations

import os
import sys


def _bootstrap_runtime_package_for_direct_script() -> None:
    if __package__:
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runtime_dir = script_dir
    while os.path.basename(runtime_dir) != "runtime":
        parent = os.path.dirname(runtime_dir)
        if parent == runtime_dir:
            return
        runtime_dir = parent
    project_root = os.path.dirname(runtime_dir)
    normalized_runtime_dir = os.path.normcase(os.path.abspath(runtime_dir))
    normalized_project_root = os.path.normcase(os.path.abspath(project_root))
    sys.path[:] = [
        entry
        for entry in sys.path
        if os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_runtime_dir
    ]
    if all(
        os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_project_root
        for entry in sys.path
    ):
        sys.path[:0] = [project_root]


_bootstrap_runtime_package_for_direct_script()

import argparse
import json
from pathlib import Path

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


def _load_vault_nodes(vault: Path) -> list[dict]:
    """Vault 디렉터리에서 모든 노드를 로드 (concepts/N-*.md YAML frontmatter)."""
    nodes = []
    # concepts/ 디렉터리에서 N-*.md 파일 검색
    for node_file in sorted(vault.rglob("N-*.md")):
        try:
            text = node_file.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            end = text.find("---", 3)
            if end < 0:
                continue
            fm_text = text[3:end].strip()
            fm = {}
            for line in fm_text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    # Skip list values (tags, sources, etc.)
                    if v.startswith("["):
                        continue
                    fm[k] = v
            node = {
                "node_id": fm.get("node_id", node_file.stem),
                "title": fm.get("title", ""),
                "spo": {
                    "subject": fm.get("title", ""),
                    "predicate": "",
                    "object": "",
                },
                "content": fm.get("content", ""),
                "metadata": {"status": fm.get("status", "ACTIVE")},
                "_filename": node_file.stem,
            }
            # body text for BM25
            body = text[end+3:].strip() if end >= 0 else ""
            node["_search_text"] = f"{fm.get('title','')} {fm.get('content','')} {body}"
            nodes.append(node)
        except RECOVERABLE_RUNTIME_ERRORS:
            continue
    return nodes


def _node_to_text(node: dict) -> str:
    """노드를 BM25 색인용 평문으로 변환."""
    parts = []
    title = node.get("title", node.get("_filename", ""))
    if title:
        parts.append(title)
    content = node.get("content", {})
    if isinstance(content, dict):
        text = content.get("text", "")
    else:
        text = str(content) if content else ""
    if text:
        parts.append(text)
    return " ".join(parts)


def bm25_search(vault: Path, query: str, top_k: int = 20) -> list[dict]:
    """순수 BM25 Okapi 검색 → JSON 직렬화 가능한 dict 목록 반환."""
    nodes = _load_vault_nodes(vault)
    if not nodes:
        return []

    corpus = [_node_to_text(n) for n in nodes]
    # Kiwi 형태소 기반 토크나이즈 (설치된 경우). fallback: char bigram
    def _tokenize(text):
        try:
            tokens = text.lower().split()
        except RECOVERABLE_RUNTIME_ERRORS:
            tokens = []
        # Kiwi 명사 추출 (한국어)
        try:
            from kiwipiepy import Kiwi
            if not hasattr(_tokenize, '_kiwi'):
                _tokenize._kiwi = Kiwi()
            for token in _tokenize._kiwi.tokenize(text):
                if token.tag in ('NNG', 'NNP', 'SL', 'XR'):
                    tokens.append(token.form)
        except ImportError:
            # Fallback: char bigram
            korean = ''.join(c for c in text if '\uac00' <= c <= '\ud7a3')
            for i in range(len(korean)-1):
                tokens.append(korean[i:i+2])
        try:
            from korean_text.query_expansion import query_expansion_tokens
            tokens.extend(query_expansion_tokens(text))
        except RECOVERABLE_RUNTIME_ERRORS:
            pass
        return tokens
    tokenized_corpus = [_tokenize(str(text)) for text in corpus]
    bm25 = BM25Okapi(tokenized_corpus)

    query_tokens = _tokenize(query)
    scores = bm25.get_scores(query_tokens)

    # 점수 기준 정렬
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    results = []
    for idx, score in ranked[:top_k]:
        if score <= 0:
            continue
        node = nodes[idx]
        results.append({
            "node_id": node.get("_filename", node.get("node_id", "")),
            "text": _node_to_text(node)[:500],
            "score": float(score),
            "bm25_score": float(score),
            "metadata": {
                "node_id": node.get("_filename", node.get("node_id", "")),
                "title": node.get("title", ""),
                "status": node.get("metadata", {}).get("status", "") if isinstance(node.get("metadata"), dict) else "",
            },
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="BM25 Bridge — vault search with JSON output")
    parser.add_argument("--vault", required=True, type=Path, help="Vault 디렉터리 경로")
    parser.add_argument("--query", required=True, type=str, help="검색 질의어")
    parser.add_argument("--top-k", type=int, default=20, help="반환할 최대 결과 수")
    args = parser.parse_args()

    if not HAS_BM25:
        print(json.dumps({
            "status": "bm25_unavailable",
            "error": "rank-bm25 not installed. Run: pip install rank-bm25",
        }))
        sys.exit(1)

    if not args.vault.exists():
        print(json.dumps({
            "status": "vault_not_found",
            "error": f"Vault not found: {args.vault}",
        }))
        sys.exit(1)

    try:
        results = bm25_search(args.vault, args.query, top_k=args.top_k)
        print(json.dumps({
            "status": "ok",
            "query": args.query,
            "result_count": len(results),
            "results": results,
        }, ensure_ascii=False))
    except RECOVERABLE_RUNTIME_ERRORS as e:
        print(json.dumps({
            "status": "error",
            "error": str(e),
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
