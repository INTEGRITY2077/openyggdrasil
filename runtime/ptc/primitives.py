"""
PTC Primitives — 오퍼레이터 SKILL이 조합할 수 있는 원시 연산.

이 모듈은 기계적 뼈대만 제공한다.
어떤 순서로 호출할지, 어떤 결과를 선택할지는
Producer/Consumer SKILL(LLM)이 결정한다.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─── 생산면 Primitives ───

def extract_decisions(context_snapshot: str) -> list[dict[str, Any]]:
    """
    context_snapshot에서 의사결정 후보를 추출한다.

    기계적 뼈대: 문장 분리 + 키워드 마커 감지
    의미적 판단: 오퍼레이터 SKILL이 결과를 필터링/보정

    Returns: [{"sentence": str, "marker": str, "confidence": float}, ...]
    """
    markers = {
        "결정": "decision",
        "확정": "decision",
        "채택": "decision",
        "폐기": "decision",
        "규칙": "policy",
        "정책": "policy",
        "앞으로": "policy",
        "반드시": "policy",
        "확인": "fact",
        "원인": "fact",
        "때문": "fact",
        "구조": "architecture",
        "설계": "architecture",
        "아키텍처": "architecture",
        "패턴": "architecture",
    }

    sentences = [s.strip() for s in context_snapshot.replace("\n", ". ").split(". ") if s.strip()]
    candidates = []

    for sentence in sentences:
        for keyword, category in markers.items():
            if keyword in sentence:
                candidates.append({
                    "sentence": sentence,
                    "marker": category,
                    "confidence": 0.0,  # SKILL이 판정
                })
                break

    return candidates


def build_spo_triples(
    decisions: list[dict[str, Any]],
    category: str,
) -> list[dict[str, str]]:
    """
    의사결정 목록에서 S-P-O 트리플을 생성한다.

    기계적 뼈대: 구조체 조립
    의미적 판단: 오퍼레이터 SKILL이 subject/predicate/object를 지정

    decisions의 각 항목에 subject, predicate, object 키가 있으면 그대로 사용.
    없으면 sentence에서 기계적으로 추출 시도.
    """
    triples = []
    for d in decisions:
        triple = {
            "subject": d.get("subject", ""),
            "predicate": d.get("predicate", ""),
            "object": d.get("object", ""),
            "category": category,
            "source_sentence": d.get("sentence", ""),
        }
        triples.append(triple)
    return triples


def build_vault_node(
    spo_triple: dict[str, str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    S-P-O 트리플을 Vault 적재 가능한 노드로 변환한다.

    기계적 뼈대: 해시 생성, 타임스탬프, 구조 조립
    """
    now = datetime.now(timezone.utc).isoformat()
    content = json.dumps(spo_triple, ensure_ascii=False, sort_keys=True)
    node_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    return {
        "node_id": f"N-{node_hash}",
        "spo": spo_triple,
        "metadata": metadata or {},
        "created_at": now,
        "content_hash": node_hash,
    }


def assign_edges(
    new_node: dict[str, Any],
    existing_nodes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """
    Q05 엣지 온톨로지에 따라 기존 노드와의 관계를 설정한다.

    기계적 뼈대: 동일 subject 감지
    의미적 판단: 오퍼레이터 SKILL이 edge_type(Supersedes/DependsOn/Contradicts)을 판정
    """
    edges = []
    new_subject = new_node["spo"].get("subject", "")

    for existing in existing_nodes:
        existing_subject = existing["spo"].get("subject", "")
        if new_subject and new_subject == existing_subject:
            edges.append({
                "from": new_node["node_id"],
                "to": existing["node_id"],
                "edge_type": "",  # SKILL이 판정
                "reason": f"동일 subject: {new_subject}",
            })

    return edges


# ─── 소비면 Primitives ───

def search_vault_by_keyword(
    vault_nodes: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """
    Vault에서 키워드 기반 검색.

    기계적 뼈대: 문자열 매칭
    의미적 판단: 오퍼레이터 SKILL이 결과 순위를 재조정
    """
    query_terms = [t for t in query.lower().split() if t]
    results = []

    for node in vault_nodes:
        spo = node.get("spo", {})
        text = f"{spo.get('subject', '')} {spo.get('predicate', '')} {spo.get('object', '')} {spo.get('source_sentence', '')}".lower()
        matched_terms = [t for t in query_terms if t in text]
        if matched_terms:
            results.append({
                **node,
                "_match_terms": matched_terms,
                "_match_score": len(matched_terms) / max(len(query_terms), 1),
            })

    results.sort(key=lambda r: r["_match_score"], reverse=True)
    return results


def search_vault_by_category(
    vault_nodes: list[dict[str, Any]],
    category: str,
) -> list[dict[str, Any]]:
    """
    Vault에서 카테고리 기반 검색.

    기계적 뼈대: 카테고리 필터
    """
    return [n for n in vault_nodes if n.get("spo", {}).get("category") == category]


def search_vault_by_edge(
    vault_nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
    target_node_id: str,
) -> list[dict[str, Any]]:
    """
    특정 노드와 연결된 노드를 엣지를 통해 검색.

    기계적 뼈대: 엣지 그래프 순회
    """
    connected_ids = set()
    for edge in edges:
        if edge["from"] == target_node_id:
            connected_ids.add(edge["to"])
        elif edge["to"] == target_node_id:
            connected_ids.add(edge["from"])

    return [n for n in vault_nodes if n["node_id"] in connected_ids]


def format_consumer_result(
    query: str,
    matched_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Consumer 검색 결과를 프로바이더가 소비할 수 있는 포맷으로 정리.

    기계적 뼈대: 구조 조립
    """
    return {
        "query": query,
        "result_count": len(matched_nodes),
        "results": [
            {
                "node_id": n["node_id"],
                "subject": n["spo"]["subject"],
                "predicate": n["spo"]["predicate"],
                "object": n["spo"]["object"],
                "category": n["spo"]["category"],
            }
            for n in matched_nodes
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Vault I/O (기계적) ───

def save_to_vault(vault_path: Path, node: dict[str, Any]) -> Path:
    """노드를 Vault에 YAML 프론트매터 Markdown으로 저장."""
    vault_path.mkdir(parents=True, exist_ok=True)
    spo = node.get("spo", {})
    category = spo.get("category", "concept")

    # Vault 서브디렉토리 결정
    type_map = {
        "decision": "concepts", "policy": "concepts",
        "fact": "entities", "architecture": "concepts",
    }
    sub_dir = vault_path / type_map.get(category, "concepts")
    sub_dir.mkdir(parents=True, exist_ok=True)

    now = node.get("created_at", datetime.now(timezone.utc).isoformat())
    date_str = now[:10] if len(now) >= 10 else now
    title = spo.get("subject", node["node_id"])[:80]
    tags_list = [category, spo.get("predicate", "")]
    tags_str = ", ".join(t for t in tags_list if t)

    frontmatter = (
        f"---\n"
        f"title: \"{title}\"\n"
        f"created: {date_str}\n"
        f"updated: {date_str}\n"
        f"type: {category}\n"
        f"status: ACTIVE\n"
        f"tags: [{tags_str}]\n"
        f"sources: []\n"
        f"node_id: \"{node['node_id']}\"\n"
        f"content_hash: \"{node.get('content_hash', '')}\"\n"
        f"---\n"
    )

    body = f"\n# {title}\n\n"
    body += f"**Category:** {category}\n\n"
    body += f"## S-P-O Triple\n\n"
    body += f"- **Subject:** {spo.get('subject', '')}\n"
    body += f"- **Predicate:** {spo.get('predicate', '')}\n"
    body += f"- **Object:** {spo.get('object', '')}\n\n"
    body += f"## Source\n\n"
    body += f"> {spo.get('source_sentence', '')}\n\n"
    body += f"## Metadata\n\n"
    body += f"```json\n{json.dumps(node.get('metadata', {}), ensure_ascii=False, indent=2)}\n```\n"

    file_path = sub_dir / f"{node['node_id']}.md"
    file_path.write_text(frontmatter + body, encoding="utf-8")
    return file_path


def load_vault(vault_path: Path) -> list[dict[str, Any]]:
    """Vault의 모든 노드를 YAML 프론트매터에서 로드."""
    if not vault_path.exists():
        return []
    nodes = []
    for f in vault_path.rglob("N-*.md"):
        text = f.read_text(encoding="utf-8")
        # Parse YAML frontmatter
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
                v = v.strip().strip('"').strip("'")
                if v.startswith("[") and v.endswith("]"):
                    v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
                fm[k.strip()] = v

        # Reconstruct node dict for search compatibility
        node = {
            "node_id": fm.get("node_id", f.stem),
            "spo": {
                "subject": fm.get("title", ""),
                "predicate": "",
                "object": "",
                "category": fm.get("type", ""),
                "source_sentence": "",
            },
            "metadata": fm,
            "created_at": fm.get("created", ""),
            "content_hash": fm.get("content_hash", ""),
        }
        # Extract S-P-O from body
        body = text[end+3:]
        for line in body.split("\n"):
            if line.startswith("- **Subject:**"):
                node["spo"]["subject"] = line.split(":**", 1)[1].strip()
            elif line.startswith("- **Predicate:**"):
                node["spo"]["predicate"] = line.split(":**", 1)[1].strip()
            elif line.startswith("- **Object:**"):
                node["spo"]["object"] = line.split(":**", 1)[1].strip()
            elif line.startswith("> ") and not node["spo"]["source_sentence"]:
                node["spo"]["source_sentence"] = line[2:].strip()
        nodes.append(node)
    return nodes


def save_edges(vault_path: Path, edges: list[dict[str, str]]) -> Path:
    """엣지 목록을 Vault에 저장."""
    vault_path.mkdir(parents=True, exist_ok=True)
    file_path = vault_path / "_edges.jsonl"
    with open(file_path, "a", encoding="utf-8") as f:
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")
    return file_path


def load_edges(vault_path: Path) -> list[dict[str, str]]:
    """Vault의 모든 엣지를 로드."""
    file_path = vault_path / "_edges.jsonl"
    if not file_path.exists():
        return []
    edges = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                edges.append(json.loads(line))
    return edges
