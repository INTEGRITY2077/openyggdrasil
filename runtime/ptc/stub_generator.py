"""
PTC Stub Generator — LLM 코드에 IPC 콜백 함수들을 주입.

도구 분류 (18종):
  Production  — find_similar, suggest_placement, get_category_tree, check_conflicts
  Consumption — deep_search, trace_evolution, get_community, rank_by_relevance
  Chain       — extract_spo, create_edge, prune_node, validate_node
  Core        — search_vault, get_all_nodes, save_note, get_node, get_edges, result
"""
from __future__ import annotations

from runtime.ptc._preamble import PREAMBLE as IPC_PREAMBLE

# batch 모드용 preamble: vault/runtime이 /tmp에 복사된 환경에서 직접 import
BATCH_PREAMBLE = """import sys, json
from pathlib import Path

sys.path = [entry for entry in sys.path if entry != "/tmp/runtime"]
if "/tmp" not in sys.path:
    sys.path[:0] = ["/tmp"]

from runtime.ptc.primitives import (
    load_vault, save_to_vault, search_vault_by_keyword,
    search_vault_bm25, build_vault_node, load_edges,
    assign_edges, save_edges, extract_decisions, build_spo_triples,
)

_VAULT = Path("/tmp/vault")

def result(data, status="ok"):
    print(json.dumps({"status": status, "result": data}, ensure_ascii=False, default=str))

# === LLM CODE BELOW ===
"""


def generate_ptc_code(llm_code: str, mode: str = "ipc") -> str:
    if mode == "ipc":
        return IPC_PREAMBLE + "\n" + llm_code
    else:
        return BATCH_PREAMBLE + "\n" + llm_code
