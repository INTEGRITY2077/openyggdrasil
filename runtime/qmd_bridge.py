"""
BM25 Bridge — 순수 BM25 Okapi 검색 CLI.

operator_entrypoint.py → subprocess.run([sys.executable, "qmd_bridge.py", ...]) → JSON stdout

의존성: rank-bm25 (numpy) — 순수 Python, 벡터 임베딩 불필요.
설치: pip install rank-bm25 (~10KB, 1초)

Usage:
    python -m runtime.qmd_bridge --vault /path/to/vault --query "검색어" [--top-k 20]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


def _load_vault_nodes(vault: Path) -> list[dict]:
    """Vault 디렉터리에서 모든 노드를 로드."""
    nodes = []
    nodes_dir = vault / "nodes"
    if nodes_dir.exists():
        for node_file in sorted(nodes_dir.glob("*.json")):
            try:
                node = json.loads(node_file.read_text(encoding="utf-8"))
                node["_filename"] = node_file.stem
                nodes.append(node)
            except (json.JSONDecodeError, ValueError):
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
    # 간단한 공백 기반 토크나이즈 (한국어/영어 혼용)
    tokenized_corpus = [text.lower().split() for text in corpus]
    bm25 = BM25Okapi(tokenized_corpus)

    query_tokens = query.lower().split()
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
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "error": str(e),
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
