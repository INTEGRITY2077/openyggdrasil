"""
PTC Primitives — 오퍼레이터 SKILL이 조합할 수 있는 원시 연산.

이 모듈은 기계적 뼈대만 제공한다.
어떤 순서로 호출할지, 어떤 결과를 선택할지는
Producer/Consumer SKILL(LLM)이 결정한다.
"""
from __future__ import annotations

import hashlib
import json
import uuid
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

    기계적 뼈대: 구조체 조립 + sentence 기반 추출
    의미적 판단: 오퍼레이터 SKILL이 subject/predicate/object를 지정

    decisions의 각 항목에 subject, predicate, object 키가 있으면 그대로 사용.
    없으면 sentence에서 기계적으로 추출.
    """
    triples = []
    for d in decisions:
        subject = d.get("subject", "")
        predicate = d.get("predicate", "")
        object_ = d.get("object", "")
        sentence = d.get("sentence", "")

        # ── sentence 기반 기계적 추출 (subject/predicate 없을 때) ──
        if not subject and sentence:
            subject = _extract_subject(sentence)
        if not predicate and sentence:
            predicate = _extract_predicate(sentence, category)

        triples.append({
            "subject": subject,
            "predicate": predicate,
            "object": object_,
            "category": category,
            "source_sentence": sentence,
        })
    return triples


def _extract_subject(sentence: str) -> str:
    """한국어 sentence에서 주어(핵심 주제)를 기계적으로 추출한다."""
    # 조사 제거 패턴: (으)로, 을/를, 은/는, 이/가, 의, 에서, 에게, 과/와
    trimmed = sentence.strip()
    # 패턴 1: "X을/를 Y하기로 결정/채택/확정" → X가 주제
    for verb_hint in ["하기로 결정", "하기로 확정", "하기로 채택", "을 결정", "를 결정",
                       "을 채택", "를 채택", "을 확정", "를 확정"]:
        if verb_hint in trimmed:
            subject = trimmed.split(verb_hint)[0].strip()
            if subject:
                return _clean_subject(subject)
    # 패턴 2: "X은/는 Y" → X가 주제
    for topic_marker in ["은 ", "는 ", "이 ", "가 "]:
        if topic_marker in trimmed:
            parts = trimmed.split(topic_marker, 1)
            if parts[0].strip():
                return _clean_subject(parts[0].strip())
    # 패턴 3: "X을/를 Y" → X가 주제
    for obj_marker in ["을 ", "를 "]:
        if obj_marker in trimmed:
            parts = trimmed.split(obj_marker, 1)
            if parts[0].strip():
                return _clean_subject(parts[0].strip())
    # 폴백: 첫 20자
    return _clean_subject(trimmed[:20])


def _clean_subject(text: str) -> str:
    """주제 문자열에서 조사와 불필요한 부분을 제거."""
    for suffix in ["으로", "로", "을", "를", "은", "는", "이", "가", "의", "에서",
                     "에게", "과", "와", "에", "도", "만", "까지", "부터", "보다"]:
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[:-len(suffix)]
    return text.strip()


def _extract_predicate(sentence: str, category: str) -> str:
    """한국어 sentence에서 술어(동작)를 기계적으로 추출한다."""
    pred_map = {
        "결정": "determined", "채택": "adopted", "확정": "confirmed",
        "도입": "introduced", "설계": "designed", "사용": "uses",
        "적용": "applied", "변경": "changed", "폐기": "deprecated",
        "통과": "routes_through", "통해": "routes_through",
        "규칙": "policy_rule", "앞으로": "policy_rule",
        "원인": "root_cause", "때문": "caused_by",
    }
    for kw, pred in pred_map.items():
        if kw in sentence:
            return pred
    return category  # 폴백: 마커 카테고리


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

    title = spo_triple.get("subject", "untitled")
    source_sentence = spo_triple.get("source_sentence", "")

    return {
        "node_id": f"N-{node_hash}",
        "title": title,
        "spo": spo_triple,
        "content": {"text": source_sentence},
        "metadata": metadata or {},
        "source": {"source_type": spo_triple.get("category", "unknown")},
        "created_at": now,
        "content_hash": node_hash,
    }


def assign_edges(
    new_node: dict[str, Any],
    existing_nodes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """
    Q05 엣지 온톨로지에 따라 기존 노드와의 관계를 설정한다.

    기계적 뼈대: 동일 subject 감지 + 키워드 오버랩 매칭
    의미적 판단: _determine_edge_type()이 Q05 6종 타입 판정
    """
    edges = []
    new_spo = new_node["spo"]
    new_subject = new_spo.get("subject", "")
    new_sentence = new_spo.get("source_sentence", "")
    new_category = new_spo.get("category", "")

    for existing in existing_nodes:
        # 자기 참조 방지
        if existing["node_id"] == new_node["node_id"]:
            continue

        existing_spo = existing["spo"]
        existing_subject = existing_spo.get("subject", "")
        existing_sentence = existing_spo.get("source_sentence", "")
        existing_category = existing_spo.get("category", "")

        # 매칭 전략 1: 정확한 subject 일치
        if new_subject and new_subject == existing_subject:
            edges.append({
                "from": new_node["node_id"],
                "to": existing["node_id"],
                "edge_type": "SUPERSEDES",
                "reason": f"동일 subject '{new_subject}' 갱신",
            })
            continue

        # 매칭 전략 2: 키워드 오버랩 (한 글자 이상 공유)
        if new_subject and existing_subject:
            overlap = _keyword_overlap(new_subject, existing_subject)
            if overlap >= 0.3:  # 30% 이상 공유
                edge_type = _determine_edge_type(
                    new_spo, existing_spo, overlap
                )
                edges.append({
                    "from": new_node["node_id"],
                    "to": existing["node_id"],
                    "edge_type": edge_type,
                    "reason": f"키워드 오버랩 {overlap:.0%}: '{new_subject}' ↔ '{existing_subject}'",
                })
                continue

        # 매칭 전략 3: sentence 간 키워드 공유 (느슨한 연관)
        if new_sentence and existing_sentence:
            sent_overlap = _keyword_overlap(new_sentence, existing_sentence)
            if sent_overlap >= 0.15:
                edge_type = _determine_edge_type(
                    new_spo, existing_spo, sent_overlap
                )
                edges.append({
                    "from": new_node["node_id"],
                    "to": existing["node_id"],
                    "edge_type": edge_type,
                    "reason": f"문장 연관성 {sent_overlap:.0%}",
                })

    return edges


def _keyword_overlap(text_a: str, text_b: str) -> float:
    """두 텍스트 간의 어휘 오버랩 비율 (0.0 ~ 1.0)."""
    words_a = set(text_a.split())
    words_b = set(text_b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    # 공백 텍스트 분할이 안 되는 한글은 문자 n-gram 비교
    if not intersection and all(len(w) > 3 for w in list(words_a)[:1]):
        # 한글: bigram overlap
        def bigrams(s):
            return {s[i:i+2] for i in range(len(s)-1)}
        bg_a = bigrams(text_a)
        bg_b = bigrams(text_b)
        if not bg_a or not bg_b:
            return 0.0
        return len(bg_a & bg_b) / min(len(bg_a), len(bg_b))
    return len(intersection) / min(len(words_a), len(words_b))


def _determine_edge_type(
    new_spo: dict, existing_spo: dict, overlap: float
) -> str:
    """
    Q05 엣지 온톨로지 6종에 따라 관계 타입을 기계적으로 판정한다.

    EdgeType (Q05):
      DEPENDS_ON   — A의 존재/실행이 B를 필수로 전제함
      SUPERSEDES   — 새로운 A가 과거의 B를 대체/무효화함
      CONTRADICTS  — A와 B가 상호 배타적이거나 충돌함
      EXTENDS      — A가 B의 아키텍처 스타일/구조를 상속받음
      IMPLEMENTS   — A(구체적 기술)가 B(패턴/인터페이스)를 실체화함
      RELATED_TO   — 상위 명시적 범주에 속하지 않으나 연관성 존재
    """
    new_cat = new_spo.get("category", "")
    existing_cat = existing_spo.get("category", "")
    new_pred = new_spo.get("predicate", "")
    existing_pred = existing_spo.get("predicate", "")

    # SUPERSEDES: 동일 카테고리 + 유의미한 오버랩 → 갱신 (결정적 항목은 v2가 v1을 대체)
    if new_cat == existing_cat and overlap >= 0.30:
        return "SUPERSEDES"

    # DEPENDS_ON: architecture 위에 다른 주제가 의존
    if existing_cat == "architecture" and new_cat != "architecture":
        return "DEPENDS_ON"

    # IMPLEMENTS: concrete thing implements a pattern
    if new_pred == "uses" and existing_pred in ("designed", "adopted"):
        return "IMPLEMENTS"

    # EXTENDS: 같은 도메인 확장
    if new_cat == existing_cat and overlap >= 0.3:
        return "EXTENDS"

    # CONTRADICTS: 서로 다른 결정/폐기
    if new_pred == "deprecated" or existing_pred == "deprecated":
        return "CONTRADICTS"
    if new_cat == "decision" and existing_cat == "decision" and overlap < 0.3:
        return "CONTRADICTS"

    # RELATED_TO: 그 외 모든 연관
    return "RELATED_TO"


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


def search_vault_bm25(
    vault_nodes: list[dict[str, Any]],
    query: str,
    *,
    top_k: int = 20,
    bm25_k1: float = 1.5,
    bm25_b: float = 0.75,
) -> list[dict[str, Any]]:
    """
    [9차 로드맵 — QMD BM25 어댑터 스터브]

    Q02 보고서 기반: BM25 Okapi 알고리즘으로 Vault 노드 검색.
    현재는 서브프로세스 QMD 연동 전 단순 문자열 폴백으로 동작.

    의도: 대규모 Vault(10,000+ 노드)에서 밀리초 단위 사전 필터링.
    향후 `subprocess` 기반 QMD CLI 래퍼로 교체 예정.

    Args:
        vault_nodes: load_vault() 반환 노드 목록
        query: 검색 질의 (한국어/영어 혼용)
        top_k: 반환할 최대 결과 수
        bm25_k1: 단어 빈도 포화도 (기본 1.5)
        bm25_b: 문서 길이 정규화 강도 (기본 0.75)

    Returns:
        _match_score 기준 상위 top_k 노드 목록
    """
    # ── QMD 연동 전 임시 폴백 ──
    results = search_vault_by_keyword(vault_nodes, query)
    results.sort(key=lambda r: r.get("_match_score", 0), reverse=True)
    top = results[:top_k]
    for node in top:
        node["_bm25_stub"] = True
        node["_bm25_params"] = {"k1": bm25_k1, "b": bm25_b}
    return top


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


def _boost_by_edges(
    results: list[dict[str, Any]],
    edges: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    [11차 마일스톤 Rev.2] SUPERSEDES to 노드를 결과에서 제거.

    생명주기 인식 부스트: SUPERSEDES 엣지의 target(to) 노드는
    상위 버전에 의해 대체된 구버전이므로 검색 결과에서 제외한다.

    Args:
        results: search_vault_bm25 반환 결과 목록
        edges: load_edges 반환 엣지 목록

    Returns:
        SUPERSEDED 노드가 제거된 결과 목록
    """
    superseded_to: set[str] = {
        e["to"] for e in edges if e.get("edge_type") == "SUPERSEDES"
    }
    return [r for r in results if r.get("node_id") not in superseded_to]


def format_consumer_result(
    query: str,
    matched_nodes: list[dict[str, Any]],
    *,
    lifecycle_status: dict[str, Any] | None = None,
    edge_context: list[dict[str, str]] | None = None,
    context_bundle_ref: str = "",
) -> dict[str, Any]:
    """
    Consumer 검색 결과를 프로바이더가 소비할 수 있는 포맷으로 정리.
    support_bundle.v1 계약을 준수한다.

    [11차 Rev.2] lifecycle_status, edge_context, context_bundle_ref 필드 추가.
    """
    return {
        "contract": "support_bundle.v1",
        "query": query,
        "anchor_type": "concept",
        "support_facts": [
            {
                "node_id": n["node_id"],
                "subject": n["spo"].get("subject", ""),
                "predicate": n["spo"].get("predicate", ""),
                "object": n["spo"].get("object", ""),
                "category": n["spo"].get("category", ""),
                "confidence": n.get("_match_score", 1.0)
            }
            for n in matched_nodes
        ],
        "source_paths": [f"N-{n.get('content_hash', '')}.md" for n in matched_nodes],
        "lifecycle_records": [],
        "lifecycle_status": lifecycle_status or {},
        "edge_context": edge_context or [],
        "context_bundle_ref": context_bundle_ref,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Vault I/O (기계적) ───

def save_to_vault(vault_path: Path, node: dict[str, Any]) -> Path:
    """노드를 Vault에 YAML 프론트매터 Markdown으로 저장."""
    from runtime.vault_guard import guard_vault_path

    vault_path.mkdir(parents=True, exist_ok=True)
    spo = node.get("spo", {})
    category = spo.get("category", "concept")

    # Vault 서브디렉토리 및 온톨로지 결정
    type_map = {
        "decision": "concepts", "policy": "concepts",
        "fact": "entities", "architecture": "concepts",
    }
    ontology_map = {
        "decision": "concept", "policy": "concept",
        "fact": "entity", "architecture": "concept",
    }
    
    sub_dir = vault_path / type_map.get(category, "concepts")
    sub_dir.mkdir(parents=True, exist_ok=True)
    mapped_type = ontology_map.get(category, "concept")

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
        f"type: {mapped_type}\n"
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


# ─── 12차 마일스톤 ───

def _validate_admission(node: dict[str, Any]) -> tuple[bool, str]:
    """
    [12차 P0] Admission Gate — Vault 진입 전 최소 품질 검증.

    contracts/admission_gate.v1.schema.json 에 정의된 최소 필드 검증.
    save_to_vault() 직전에 호출되어 부적격 노드를 걸러낸다.

    초기 버전: title/category 존재 + content.text 비어있지 않음 검증.
    source_type은 선택적(레거시 호환).

    Args:
        node: build_vault_node()가 생성한 노드 딕셔너리

    Returns:
        (통과 여부, 실패 사유)
    """
    # title 또는 category 검증 (SPO 구조 호환)
    title = node.get("title", "") or node.get("category", "")
    if not title or not title.strip():
        return False, "title 누락 또는 빈 문자열"

    # content.text 검증
    content = node.get("content", {})
    if isinstance(content, dict):
        text = content.get("text", "")
        if not text or not text.strip():
            return False, "content.text 누락 또는 빈 문자열"

    return True, "ok"


def _run_feedback_loop(mailbox: Path) -> dict[str, int]:
    """
    [12차 P1] 피드백 루프 — Gardener receipts → prune/curate intent 자동 발행.

    Gardener가 발행한 receipts.jsonl을 읽어 prune/curate 필요성을 판단하고
    해당 intent를 intents.jsonl에 추가한다. _handle_prune()을 재활용한다.

    Args:
        mailbox: 메일박스 디렉터리 경로

    Returns:
        처리 통계 {"prune_issued": N, "curate_issued": N, "errors": N}
    """
    gardener_receipts = mailbox / "gardener_receipts.jsonl"
    if not gardener_receipts.exists():
        return {"prune_issued": 0, "curate_issued": 0, "errors": 0}

    from datetime import datetime as _dt
    from datetime import timezone as _tz

    stats = {"prune_issued": 0, "curate_issued": 0, "errors": 0}
    intents_file = mailbox / "intents.jsonl"

    for line in gardener_receipts.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            receipt = json.loads(line)
        except json.JSONDecodeError:
            stats["errors"] += 1
            continue

        action = receipt.get("action", "")
        node_id = receipt.get("node_id", "")
        if not node_id:
            continue

        if action in ("prune", "curate"):
            intent = {
                "mail_id": f"feedback-{uuid.uuid4().hex[:8]}",
                "intent": action,
                "payload": {"node_id": node_id, "topic_hint": receipt.get("topic_hint", "")},
                "timestamp": _dt.now(_tz.utc).isoformat(),
                "source": "feedback_loop",
            }
            with open(intents_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(intent, ensure_ascii=False) + "\n")
            if action == "prune":
                stats["prune_issued"] += 1
            else:
                stats["curate_issued"] += 1

    return stats
