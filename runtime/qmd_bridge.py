"""
QMD Bridge — qmd search --json 서브프로세스 진입점.

operator_entrypoint.py → subprocess.run([sys.executable, "qmd_bridge.py", ...]) → JSON stdout

Usage:
    python -m runtime.qmd_bridge --vault /path/to/vault --query "검색어" [--top-k 20]

설치:
    pip install qmd  (또는 /tmp/qmd-venv/bin/python 으로 호출)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from qmd import QmdClient
    HAS_QMD = True
except ImportError:
    HAS_QMD = False


def _vault_db_path(vault: Path) -> Path:
    """Vault 디렉터리 내 QMD 데이터베이스 경로."""
    return vault / ".qmd" / "vault.db"


def _index_vault(client: QmdClient, vault: Path) -> str:
    """Vault 노드를 QMD 컬렉션에 인덱싱. 컬렉션명을 반환."""
    import json as _json

    collection_name = "vault"
    nodes_dir = vault / "nodes"
    if not nodes_dir.exists():
        return collection_name

    col = client.collection(collection_name)
    existing = set(col.list_documents())

    for node_file in sorted(nodes_dir.glob("*.json")):
        node_id = node_file.stem
        if node_id in existing:
            continue
        try:
            node = _json.loads(node_file.read_text(encoding="utf-8"))
        except (_json.JSONDecodeError, ValueError):
            continue

        # 마크다운 본문 구성 (검색 대상)
        title = node.get("title", node_id)
        content = node.get("content", {}).get("text", "")
        markdown = f"# {title}\n\n{content}"

        # 메타데이터 추출
        metadata = {
            "node_id": node_id,
            "title": title,
            "status": node.get("metadata", {}).get("status", ""),
            "created": node.get("created_at", ""),
            "source": node.get("source", {}).get("source_type", ""),
        }

        col.add_document(node_id, markdown, metadata)
        existing.add(node_id)

    return collection_name


def qmd_search(vault: Path, query: str, top_k: int = 20) -> list[dict]:
    """QMD hybrid_search 호출 → JSON 직렬화 가능한 dict 목록 반환."""
    db_path = _vault_db_path(vault)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    client = QmdClient(str(db_path))
    try:
        collection_name = _index_vault(client, vault)
        col = client.collection(collection_name)
        results = col.hybrid_search(query, top_k=top_k, rerank=True)

        return [
            {
                "node_id": r.chunk_ref.document_id,
                "text": r.text[:500],
                "score": r.score,
                "bm25_score": r.bm25_score,
                "vector_score": r.vector_score,
                "rerank_score": r.rerank_score,
                "metadata": r.metadata,
            }
            for r in results
        ]
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="QMD Bridge — vault search with JSON output")
    parser.add_argument("--vault", required=True, type=Path, help="Vault 디렉터리 경로")
    parser.add_argument("--query", required=True, type=str, help="검색 질의어")
    parser.add_argument("--top-k", type=int, default=20, help="반환할 최대 결과 수")
    args = parser.parse_args()

    if not HAS_QMD:
        print(json.dumps({
            "status": "qmd_unavailable",
            "error": "qmd package not installed. Run: pip install qmd",
        }))
        sys.exit(1)

    if not args.vault.exists():
        print(json.dumps({
            "status": "vault_not_found",
            "error": f"Vault not found: {args.vault}",
        }))
        sys.exit(1)

    try:
        results = qmd_search(args.vault, args.query, top_k=args.top_k)
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
