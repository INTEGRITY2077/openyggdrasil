"""
PTC IPC Server — Unix Domain Socket 기반 primitive dispatch.

bwrap 샌드박스 안의 LLM 코드가 Unix 소켓으로 호스트에 콜백하여
primitives를 호출할 수 있게 한다.

Protocol: JSON-line (한 줄 = 하나의 요청/응답)
  Request:  {"id": N, "method": "...", "kwargs": {...}}
  Response: {"id": N, "result": ...} or {"id": N, "error": "..."}

PTC 도구 (18종):
  Production  — find_similar, suggest_placement, check_conflicts, get_category_tree
  Consumption — deep_search, trace_evolution, get_community, rank_by_relevance
  Chain       — extract_spo, create_edge, prune_node, validate_node
  Core        — load_vault, search, save_note, load_edges, get_node
"""
from __future__ import annotations

import json
import socket
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


_primitives_cache = None


def _load_primitives():
    """primitives 모듈 지연 로딩 (캐싱)."""
    global _primitives_cache
    if _primitives_cache is not None:
        return _primitives_cache
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ptc.primitives import (
        load_vault,
        save_to_vault,
        search_vault_by_keyword,
        search_vault_by_category,
        search_vault_by_edge,
        search_vault_bm25,
        build_vault_node,
        load_edges,
        _boost_by_edges,
        _determine_edge_type,
    )
    _primitives_cache = (
        load_vault, save_to_vault,
        search_vault_by_keyword, search_vault_by_category,
        search_vault_by_edge, search_vault_bm25,
        build_vault_node, load_edges, _boost_by_edges, _determine_edge_type,
    )
    return _primitives_cache


# ─── 생산면 PTC 도구 ───

def _find_similar(vault: Path, subject: str, limit: int = 10) -> dict:
    p = _load_primitives()
    load_vault, _, search_kw, _, _, _, _, load_edges, _boost, _ = p
    nodes = load_vault(vault)
    edges = load_edges(vault)
    kw_matches = search_kw(nodes, subject)
    boosted = _boost(kw_matches, edges) if kw_matches else []
    categories = defaultdict(list)
    for n in boosted[:limit]:
        cat = n.get("spo", {}).get("category", "unknown")
        categories[cat].append(n.get("node_id"))
    return {
        "matches": [
            {"node_id": n.get("node_id"), "subject": n.get("spo", {}).get("subject", ""),
             "category": n.get("spo", {}).get("category", ""),
             "score": n.get("_match_score", n.get("_bm25_score", 0))}
            for n in boosted[:limit]
        ],
        "category_distribution": {k: len(v) for k, v in categories.items()},
        "total_candidates": len(kw_matches),
    }


def _suggest_placement(vault: Path, subject: str, content: str) -> dict:
    p = _load_primitives()
    load_vault, _, _, _, _, _, _, load_edges, _, _ = p
    nodes = load_vault(vault)
    edges = load_edges(vault)
    from ptc.primitives import search_vault_by_keyword
    similar = search_vault_by_keyword(nodes, subject)
    if not similar:
        similar = search_vault_by_keyword(nodes, content[:100] if content else subject)
    cat_counts = defaultdict(int)
    for n in similar[:20]:
        cat = n.get("spo", {}).get("category", "unknown")
        cat_counts[cat] += 1
    best_cat = max(cat_counts, key=cat_counts.get) if cat_counts else "concept"
    best_count = cat_counts.get(best_cat, 0)
    conflicts = []
    edge_index = defaultdict(list)
    for e in edges:
        edge_index[e.get("from", "")].append(e)
        edge_index[e.get("to", "")].append(e)
    for n in similar[:5]:
        nid = n.get("node_id", "")
        for e in edge_index.get(nid, []):
            if e.get("edge_type") in ("SUPERSEDES", "CONTRADICTS"):
                other = e.get("to") if e.get("from") == nid else e.get("from")
                conflicts.append({"existing_node": nid, "existing_subject": n.get("spo", {}).get("subject", ""),
                                 "edge_type": e.get("edge_type"), "related_to": other})
    return {
        "suggested_category": best_cat,
        "category_confidence": min(best_count / len(similar), 1.0) if similar else 0,
        "category_alternatives": sorted(cat_counts.items(), key=lambda x: -x[1])[:3],
        "similar_count": len(similar),
        "conflicts": conflicts,
        "top_similar": [{"node_id": n.get("node_id"), "subject": n.get("spo", {}).get("subject", ""),
                         "category": n.get("spo", {}).get("category", "")} for n in similar[:5]],
    }


def _get_category_tree(vault: Path) -> dict:
    p = _load_primitives()
    load_vault, _, _, _, _, _, _, _, _, _ = p
    nodes = load_vault(vault)
    tree = defaultdict(list)
    for n in nodes:
        cat = n.get("spo", {}).get("category", "unknown")
        tree[cat].append({"node_id": n.get("node_id"), "subject": n.get("spo", {}).get("subject", "")})
    return {"categories": list(tree.keys()), "category_counts": {k: len(v) for k, v in tree.items()}, "total_nodes": len(nodes)}


# ─── 소비면 PTC 도구 ───

def _deep_search(vault: Path, topic: str, max_depth: int = 3, limit: int = 20) -> dict:
    p = _load_primitives()
    load_vault, _, search_kw, _, _, _, _, load_edges, _, _ = p
    nodes = load_vault(vault)
    edges = load_edges(vault)
    adj = defaultdict(list)
    node_map = {n["node_id"]: n for n in nodes}
    for e in edges:
        adj[e.get("from", "")].append((e.get("to", ""), e.get("edge_type", "RELATED_TO")))
        adj[e.get("to", "")].append((e.get("from", ""), e.get("edge_type", "RELATED_TO")))
    seeds = search_kw(nodes, topic)[:5]
    if not seeds:
        return {"trail": [], "visited": 0, "depth_reached": 0}
    visited = set()
    trail = []
    queue = [(n["node_id"], 0, "seed") for n in seeds]
    while queue and len(trail) < limit:
        nid, depth, via = queue.pop(0)
        if nid in visited or depth > max_depth:
            continue
        visited.add(nid)
        node = node_map.get(nid, {})
        trail.append({"node_id": nid, "subject": node.get("spo", {}).get("subject", ""),
                      "category": node.get("spo", {}).get("category", ""), "depth": depth, "via": via})
        for neighbor, etype in adj.get(nid, []):
            if neighbor not in visited:
                queue.append((neighbor, depth + 1, etype))
    return {"trail": trail, "visited": len(visited),
            "depth_reached": max(t["depth"] for t in trail) if trail else 0,
            "seed_subjects": [node_map.get(s["node_id"], {}).get("spo", {}).get("subject", "") for s in seeds if s["node_id"] in node_map]}


def _trace_evolution(vault: Path, node_id: str) -> dict:
    p = _load_primitives()
    load_vault, _, _, _, _, _, _, load_edges, _, _ = p
    nodes = load_vault(vault)
    edges = load_edges(vault)
    node_map = {n["node_id"]: n for n in nodes}
    forward, backward = [], []
    for e in edges:
        if e.get("edge_type") != "SUPERSEDES":
            continue
        if e.get("from") == node_id:
            target = node_map.get(e.get("to", ""), {})
            forward.append({"node_id": e.get("to"), "subject": target.get("spo", {}).get("subject", ""), "direction": "superseded_by_this"})
        if e.get("to") == node_id:
            source = node_map.get(e.get("from", ""), {})
            backward.append({"node_id": e.get("from"), "subject": source.get("spo", {}).get("subject", ""), "direction": "supersedes_this"})
    current = node_map.get(node_id, {})
    return {"current": {"node_id": node_id, "subject": current.get("spo", {}).get("subject", "")},
            "superseded": forward, "superseded_by": backward, "evolution_chain_length": len(forward) + len(backward)}


def _get_community(vault: Path, node_id: str, radius: int = 2) -> dict:
    p = _load_primitives()
    load_vault, _, _, _, _, _, _, load_edges, _, _ = p
    nodes = load_vault(vault)
    edges = load_edges(vault)
    node_map = {n["node_id"]: n for n in nodes}
    adj = defaultdict(list)
    for e in edges:
        adj[e.get("from", "")].append((e.get("to", ""), e.get("edge_type", "RELATED_TO")))
        adj[e.get("to", "")].append((e.get("from", ""), e.get("edge_type", "RELATED_TO")))
    visited = set()
    community = []
    queue = [(node_id, 0)]
    while queue:
        nid, depth = queue.pop(0)
        if nid in visited or depth > radius:
            continue
        visited.add(nid)
        node = node_map.get(nid, {})
        if nid != node_id:
            community.append({"node_id": nid, "subject": node.get("spo", {}).get("subject", ""),
                             "category": node.get("spo", {}).get("category", ""), "distance": depth})
        for neighbor, _ in adj.get(nid, []):
            if neighbor not in visited:
                queue.append((neighbor, depth + 1))
    return {"center_node_id": node_id, "community_size": len(community), "radius": radius, "members": community}


# ─── Chain Completion: 고정 체인 각 단계를 PTC로 호출 가능하게 ───

def _extract_spo(vault: Path, text: str) -> dict:
    from ptc.primitives import extract_decisions, build_spo_triples
    decisions = extract_decisions(text)
    if not decisions:
        return {"triples": [], "count": 0}
    triples = build_spo_triples(decisions, "ptc_extraction")
    return {"triples": triples, "count": len(triples)}


def _create_edge(vault: Path, from_id: str, to_id: str, edge_type: str = "RELATED_TO") -> dict:
    from ptc.primitives import save_edges
    edge = {"from": from_id, "to": to_id, "edge_type": edge_type}
    save_edges(vault, [edge])
    return {"edge": edge, "status": "created"}


def _prune_node(vault: Path, node_id: str) -> dict:
    from runtime.vault_guard import guard_vault_path
    import shutil as _shutil

    archive_dir = vault.parent / "archive" / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_dir.mkdir(parents=True, exist_ok=True)
    pruned = False
    for md_file in vault.rglob(node_id + ".md"):
        # vault_guard: 대상 파일이 vault 내부인지 검증
        try:
            guard_vault_path(vault, md_file.relative_to(vault))
        except ValueError:
            continue  # vault 외부 파일은 건드리지 않음
        _shutil.move(str(md_file), str(archive_dir / md_file.name))
        pruned = True
    return {"node_id": node_id, "pruned": pruned, "archive": str(archive_dir)}


def _validate_node(vault: Path, subject: str, predicate: str = "", obj: str = "", category: str = "concept") -> dict:
    p = _load_primitives()
    build_vault_node = p[6]  # index 6 = build_vault_node
    from ptc.primitives import _validate_admission
    spo = {"subject": subject, "predicate": predicate, "object": obj, "category": category,
           "source_sentence": f"{predicate} {obj}"}
    node = build_vault_node(spo, metadata={"provider_id": "ptc"})
    passed, reason = _validate_admission(node)
    return {"passed": passed, "reason": reason, "node_id": node.get("node_id")}


# ─── Dispatch ───


# ─── PTC Retrieval Handlers ───

def _ptc_locate_region(vault, query_text):
    try:
        from retrieval.pathfinder_tools import locate_region
        return locate_region(query_text=query_text, vault_root=vault)
    except Exception as e:
        return {"error": str(e), "method": "locate_region"}

def _ptc_select_topic_anchor(vault, query_text, region_id):
    try:
        from retrieval.pathfinder_tools import select_topic_anchor
        return select_topic_anchor(query_text=query_text, region_id=region_id, vault_root=vault)
    except Exception as e:
        return {"error": str(e), "method": "select_topic_anchor"}

def _ptc_read_origin_claims(vault, topic_id, limit):
    try:
        from retrieval.pathfinder_tools import get_origin_claims
        return get_origin_claims(topic_id=topic_id, vault_root=vault, limit=limit)
    except Exception as e:
        return {"error": str(e), "method": "read_origin_claims"}

def _ptc_read_recent_claims(vault, topic_id, limit):
    try:
        from retrieval.pathfinder_tools import read_recent_claims
        return read_recent_claims(topic_id=topic_id, vault_root=vault, limit=limit)
    except Exception as e:
        return {"error": str(e), "method": "read_recent_claims"}

def _ptc_collect_claim_ids(origin_rows, recent_rows):
    try:
        from retrieval.ptc_tools.collect_claim_ids import collect_claim_ids
        return collect_claim_ids(origin_rows=origin_rows, recent_rows=recent_rows)
    except Exception as e:
        return {"error": str(e), "method": "collect_claim_ids"}

def _ptc_read_source_paths(vault, topic_id, claim_ids):
    try:
        from retrieval.pathfinder_tools import read_source_paths
        return read_source_paths(topic_id=topic_id, claim_ids=claim_ids, vault_root=vault)
    except Exception as e:
        return {"error": str(e), "method": "read_source_paths"}

def _ptc_assemble_support_bundle(query_text, anchor, origin_rows, recent_rows, source_paths):
    try:
        from retrieval.pathfinder_tools import build_support_bundle
        return build_support_bundle(query_text=query_text, anchor=anchor,
                                    origin_rows=origin_rows, recent_rows=recent_rows,
                                    source_paths=source_paths)
    except Exception as e:
        return {"error": str(e), "method": "assemble_support_bundle"}

def _ptc_assemble_unanchored_bundle(query_text):
    try:
        from retrieval.pathfinder_tools import assemble_unanchored_bundle
        return assemble_unanchored_bundle(query_text=query_text)
    except Exception as e:
        return {"error": str(e), "method": "assemble_unanchored_bundle"}


def _dispatch(method: str, kwargs: dict, vault: Path) -> dict:
    p = _load_primitives()
    load_vault, save_to_vault, _, _, _, search_bm25, build_vault_node, load_edges, _, _ = p

    if method == "load_vault":
        nodes = load_vault(vault)
        return {"nodes": nodes, "count": len(nodes)}
    elif method == "search_vault_by_keyword":
        nodes = load_vault(vault)
        matches = p[2](nodes, kwargs.get("keyword", ""))
        return {"nodes": matches, "count": len(matches)}
    elif method == "search_vault_bm25":
        nodes = load_vault(vault)
        matches = search_bm25(nodes, kwargs.get("query", ""))
        return {"nodes": matches[:kwargs.get("top_k", 20)], "count": len(matches)}
    elif method == "save_vault_note":
        content_text = kwargs.get("content", "")
        spo = {"subject": kwargs.get("subject", ""), "predicate": "notes",
               "object": content_text, "category": kwargs.get("category", "concept"),
               "source_sentence": content_text}
        node = build_vault_node(spo, metadata={"provider_id": kwargs.get("provider_id", "ptc_sandbox")})
        path = save_to_vault(vault, node)
        return {"node_id": node.get("node_id"), "path": str(path), "status": "saved"}
    elif method == "load_edges":
        edges = load_edges(vault)
        return {"edges": edges, "count": len(edges)}
    elif method == "get_node":
        node_id = kwargs.get("node_id", "")
        nodes = load_vault(vault)
        for n in nodes:
            if n.get("node_id") == node_id:
                return {"node": n, "found": True}
        return {"node": None, "found": False}
    elif method == "find_similar":
        return _find_similar(vault, kwargs.get("subject", ""), kwargs.get("limit", 10))
    elif method == "suggest_placement":
        return _suggest_placement(vault, kwargs.get("subject", ""), kwargs.get("content", ""))
    elif method == "get_category_tree":
        return _get_category_tree(vault)
    elif method == "check_conflicts":
        result = _suggest_placement(vault, kwargs.get("subject", ""), "")
        return {"conflicts": result["conflicts"], "conflict_count": len(result["conflicts"])}
    elif method == "deep_search":
        return _deep_search(vault, kwargs.get("topic", ""), kwargs.get("max_depth", 3), kwargs.get("limit", 20))
    elif method == "trace_evolution":
        return _trace_evolution(vault, kwargs.get("node_id", ""))
    elif method == "get_community":
        return _get_community(vault, kwargs.get("node_id", ""), kwargs.get("radius", 2))
    elif method == "rank_by_relevance":
        nodes = load_vault(vault)
        edges = load_edges(vault)
        topic = kwargs.get("topic", "")
        from ptc.primitives import search_vault_by_keyword
        matches = search_vault_by_keyword(nodes, topic)
        boosted = p[8](matches, edges) if matches else []
        return {"ranked": [{"node_id": n.get("node_id"), "subject": n.get("spo", {}).get("subject", ""),
                           "score": n.get("_match_score", 0)} for n in boosted[:kwargs.get("limit", 10)]], "total": len(boosted)}
    # Chain completion
    elif method == "extract_spo":
        return _extract_spo(vault, kwargs.get("text", ""))
    elif method == "create_edge":
        return _create_edge(vault, kwargs.get("from_id", ""), kwargs.get("to_id", ""), kwargs.get("edge_type", "RELATED_TO"))
    elif method == "prune_node":
        return _prune_node(vault, kwargs.get("node_id", ""))
    elif method == "validate_node":
        return _validate_node(vault, kwargs.get("subject", ""), kwargs.get("predicate", ""),
                             kwargs.get("object", ""), kwargs.get("category", "concept"))
    # PTC Retrieval (README 9-step palette)
    elif method == "locate_region":
        return _ptc_locate_region(vault, kwargs.get("query_text", ""))
    elif method == "select_topic_anchor":
        return _ptc_select_topic_anchor(vault, kwargs.get("query_text", ""), kwargs.get("region_id"))
    elif method == "read_origin_claims":
        return _ptc_read_origin_claims(vault, kwargs.get("topic_id", ""), kwargs.get("limit", 1))
    elif method == "read_recent_claims":
        return _ptc_read_recent_claims(vault, kwargs.get("topic_id", ""), kwargs.get("limit", 3))
    elif method == "collect_claim_ids":
        return _ptc_collect_claim_ids(kwargs.get("origin_rows", []), kwargs.get("recent_rows", []))
    elif method == "read_source_paths":
        return _ptc_read_source_paths(vault, kwargs.get("topic_id", ""), kwargs.get("claim_ids"))
    elif method == "assemble_support_bundle":
        return _ptc_assemble_support_bundle(kwargs.get("query_text", ""), kwargs.get("anchor", {}),
                                            kwargs.get("origin_rows", []), kwargs.get("recent_rows", []),
                                            kwargs.get("source_paths", []))
    elif method == "assemble_unanchored_bundle":
        return _ptc_assemble_unanchored_bundle(kwargs.get("query_text", ""))
    else:
        return {"error": f"unknown method: {method}"}


# ─── IPC Server ───

class PTCIpcServer:
    def __init__(self, socket_path: str, vault: Path, timeout: float = 120):
        self.socket_path = socket_path
        self.vault = vault
        self.timeout = timeout
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        Path(self.socket_path).unlink(missing_ok=True)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.socket_path)
        self._server.listen(1)
        self._server.settimeout(self.timeout)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _serve(self) -> None:
        self._ready.set()
        try:
            while True:
                try:
                    conn, _ = self._server.accept()
                    self._handle_client(conn)
                except socket.timeout:
                    break
        except Exception as e:
            import sys; print(f"[ipc_server] serve error: {e}", file=sys.stderr)
        finally:
            try: self._server.close()
            except Exception as e:
                import sys; print(f"[ipc_server] close error: {e}", file=sys.stderr)
            Path(self.socket_path).unlink(missing_ok=True)

    def _handle_client(self, conn: socket.socket) -> None:
        conn.settimeout(self.timeout)
        buf = b""
        while True:
            try:
                chunk = conn.recv(4096)
                if not chunk: break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip(): continue
                    try:
                        request = json.loads(line.decode("utf-8"))
                        result = _dispatch(request.get("method", ""), request.get("kwargs", {}), self.vault)
                        response = {"id": request.get("id", 0), "result": result}
                    except Exception as e:
                        response = {"id": 0, "error": str(e)}
                    conn.sendall(json.dumps(response, ensure_ascii=False, default=str).encode() + b"\n")
            except socket.timeout:
                break
            except Exception:
                break

    def stop(self) -> None:
        try:
            if self._server: self._server.close()
        except Exception as e:
            import sys; print(f"[ipc_server] stop error: {e}", file=sys.stderr)
        Path(self.socket_path).unlink(missing_ok=True)

    def __enter__(self): self.start(); return self
    def __exit__(self, *args): self.stop()
