# PTC Preamble - LLM code injection with affordance-based tool descriptions
# This is injected into LLM sandbox code by stub_generator.py

from __future__ import annotations

from runtime.ptc.preamble_facades import (
    PATHFINDER_FACADE_IMPLEMENTATION_MAP,
    PATHFINDER_FACADE_METHOD_MAP,
    PATHFINDER_IMPLEMENTATION_MODULE,
    render_pathfinder_preamble_facades,
)


def pathfinder_facade_implementation_map() -> dict[str, str]:
    return dict(PATHFINDER_FACADE_IMPLEMENTATION_MAP)


def pathfinder_facade_method_map() -> dict[str, str]:
    return dict(PATHFINDER_FACADE_METHOD_MAP)


_PREAMBLE_PREFIX = r"""import socket, json, os, sys
from pathlib import Path

_PTC_SOCK = "/tmp/ptc.sock"
_call_id = 0
_PTC_RECOVERABLE_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    RuntimeError,
    ImportError,
    TimeoutError,
    UnicodeError,
    json.JSONDecodeError,
)


def _ptc_call(method, **kwargs):
    global _call_id
    _call_id += 1
    request = json.dumps({"id": _call_id, "method": method, "kwargs": kwargs})
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect(_PTC_SOCK)
        sock.sendall(request.encode("utf-8") + b"\n")
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk: break
            buf += chunk
        sock.close()
        response = json.loads(buf.decode("utf-8"))
        if response.get("error"): raise RuntimeError(response["error"])
        return response.get("result", {})
    except FileNotFoundError:
        return {"error": "socket_unavailable"}
    except _PTC_RECOVERABLE_ERRORS as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
# PTC Tool Palette (26 tools)
# Freely combine. Each tool declares its affordance.
# ═══════════════════════════════════════════════════════════

def result(data, status="ok"):
    '''Final output. Call this once at the end.
    Use this when: all tool calls are complete and you have the final result.
    Do NOT use when: you still need to call more tools.'''
    print(json.dumps({"status": status, "result": data}, ensure_ascii=False, default=str))


# === SEARCH ===

def deep_search(topic, max_depth=3, limit=20):
    '''BM25 + edge BFS comprehensive search.
    Use this when: you need a broad Vault exploration with related nodes.
    Do NOT use when: you need specific provenance traces -> use read_origin_claims.
    If ambiguous: prefer deep_search for general queries.'''
    return _ptc_call("deep_search", topic=topic, max_depth=max_depth, limit=limit)

def search_vault(keyword):
    '''Fast BM25 keyword matching.
    Use this when: you need quick keyword-based candidate nodes.
    Do NOT use when: you need semantic or graph-based search -> use deep_search.'''
    r = _ptc_call("search_vault_by_keyword", keyword=keyword)
    return r.get("nodes", [])
"""

_PREAMBLE_SUFFIX = r"""# === PRODUCTION ===

def find_similar(subject, limit=10):
    '''Find nodes similar to given subject.
    Use this when: checking for duplicate knowledge before saving.'''
    r = _ptc_call("find_similar", subject=subject, limit=limit)
    return r.get("matches", [])

def suggest_placement(subject, content=""):
    '''Suggest where a new node should be placed in the Vault.
    Use this when: saving new knowledge and unsure about category.'''
    return _ptc_call("suggest_placement", subject=subject, content=content)

def get_category_tree():
    '''Get the Vault category tree structure.
    Use this when: exploring available categories.'''
    return _ptc_call("get_category_tree")

def check_conflicts(subject):
    '''Check if subject conflicts with existing nodes.
    Use this when: verifying before saving potentially conflicting knowledge.'''
    r = _ptc_call("check_conflicts", subject=subject)
    return r.get("conflicts", [])

# === GRAPH ===

def trace_evolution(node_id):
    '''Trace how a node evolved over time.
    Use this when: understanding knowledge lineage.'''
    return _ptc_call("trace_evolution", node_id=node_id)

def get_community(node_id, radius=2):
    '''Get the graph community around a node.
    Use this when: exploring related knowledge clusters.'''
    r = _ptc_call("get_community", node_id=node_id, radius=radius)
    return r.get("members", [])

def rank_by_relevance(topic, limit=10):
    '''Rank nodes by relevance to a topic using BM25 + edge boost.
    Use this when: you need scored and sorted results.'''
    r = _ptc_call("rank_by_relevance", topic=topic, limit=limit)
    return r.get("ranked", [])

# === CHAIN ===

def extract_spo(text):
    '''Extract Subject-Predicate-Object triples from text.
    Use this when: analyzing raw text for knowledge extraction.'''
    r = _ptc_call("extract_spo", text=text)
    return r.get("triples", [])

def create_edge(from_id, to_id, edge_type="RELATED_TO"):
    '''Create an edge between two nodes.
    Use this when: linking related knowledge in the graph.'''
    return _ptc_call("create_edge", from_id=from_id, to_id=to_id, edge_type=edge_type)

def prune_node(node_id):
    '''Mark a node as SUPERSEDED.
    Use this when: knowledge is outdated and should be archived.'''
    return _ptc_call("prune_node", node_id=node_id)

def validate_node(subject, predicate="", object="", category="concept"):
    '''Validate a node before saving.
    Use this when: checking node quality before save_note.'''
    return _ptc_call("validate_node", subject=subject, predicate=predicate, object=object, category=category)

# === CORE ===

def get_all_nodes():
    '''Get all nodes from the Vault.
    Use this when: you need the complete knowledge graph.'''
    r = _ptc_call("load_vault")
    return r.get("nodes", [])

def get_node(node_id):
    '''Get a single node by ID.
    Use this when: you need one specific node.'''
    r = _ptc_call("get_node", node_id=node_id)
    return r.get("node") if r.get("found") else None

def save_note(subject, content, category="concept"):
    '''Save a new node to the Vault.
    Use this when: creating new knowledge entries.'''
    return _ptc_call("save_vault_note", subject=subject, content=content, category=category)

def get_edges():
    '''Get all edges from the Vault.
    Use this when: you need the relationship graph.'''
    r = _ptc_call("load_edges")
    return r.get("edges", [])

# === LLM CODE BELOW ===
"""


def build_preamble() -> str:
    return (
        _PREAMBLE_PREFIX
        + "\n# === PROVENANCE TRACE ===\n\n"
        + render_pathfinder_preamble_facades()
        + "\n\n"
        + _PREAMBLE_SUFFIX
    )


PREAMBLE = build_preamble()


__all__ = [
    "PATHFINDER_IMPLEMENTATION_MODULE",
    "PREAMBLE",
    "build_preamble",
    "pathfinder_facade_implementation_map",
    "pathfinder_facade_method_map",
]
