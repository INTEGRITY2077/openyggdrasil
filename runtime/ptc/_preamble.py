# Auto-generated PTC preamble - do not edit directly
# This is the code injected into LLM sandbox code

PREAMBLE = """import socket, json, os, sys
from pathlib import Path

_PTC_SOCK = "/tmp/ptc.sock"
_call_id = 0


def _ptc_call(method, **kwargs):
    global _call_id
    _call_id += 1
    request = json.dumps({"id": _call_id, "method": method, "kwargs": kwargs})
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect(_PTC_SOCK)
        sock.sendall(request.encode("utf-8") + b\"\\n\")
        buf = b\"\"
        while b\"\\n\" not in buf:
            chunk = sock.recv(4096)
            if not chunk: break
            buf += chunk
        sock.close()
        response = json.loads(buf.decode("utf-8"))
        if response.get("error"): raise RuntimeError(response["error"])
        return response.get("result", {})
    except FileNotFoundError:
        return {"error": "socket_unavailable"}
    except Exception as e:
        return {"error": str(e)}


# === PRODUCTION ===

def find_similar(subject, limit=10):
    r = _ptc_call("find_similar", subject=subject, limit=limit)
    return r.get("matches", [])

def suggest_placement(subject, content=""):
    return _ptc_call("suggest_placement", subject=subject, content=content)

def get_category_tree():
    return _ptc_call("get_category_tree")

def check_conflicts(subject):
    r = _ptc_call("check_conflicts", subject=subject)
    return r.get("conflicts", [])


# === CONSUMPTION ===

def deep_search(topic, max_depth=3, limit=20):
    return _ptc_call("deep_search", topic=topic, max_depth=max_depth, limit=limit)

def trace_evolution(node_id):
    return _ptc_call("trace_evolution", node_id=node_id)

def get_community(node_id, radius=2):
    r = _ptc_call("get_community", node_id=node_id, radius=radius)
    return r.get("members", [])

def rank_by_relevance(topic, limit=10):
    r = _ptc_call("rank_by_relevance", topic=topic, limit=limit)
    return r.get("ranked", [])


# === CHAIN COMPLETION ===

def extract_spo(text):
    r = _ptc_call("extract_spo", text=text)
    return r.get("triples", [])

def create_edge(from_id, to_id, edge_type="RELATED_TO"):
    return _ptc_call("create_edge", from_id=from_id, to_id=to_id, edge_type=edge_type)

def prune_node(node_id):
    return _ptc_call("prune_node", node_id=node_id)

def validate_node(subject, predicate="", object="", category="concept"):
    return _ptc_call("validate_node", subject=subject, predicate=predicate, object=object, category=category)


# === CORE ===

def search_vault(keyword):
    r = _ptc_call("search_vault_by_keyword", keyword=keyword)
    return r.get("nodes", [])

def get_all_nodes():
    r = _ptc_call("load_vault")
    return r.get("nodes", [])

def get_node(node_id):
    r = _ptc_call("get_node", node_id=node_id)
    return r.get("node") if r.get("found") else None

def save_note(subject, content, category="concept"):
    return _ptc_call("save_vault_note", subject=subject, content=content, category=category)

def get_edges():
    r = _ptc_call("load_edges")
    return r.get("edges", [])

def result(data, status="ok"):
    print(json.dumps({"status": status, "result": data}, ensure_ascii=False, default=str))


# === LLM CODE BELOW ===
"""
