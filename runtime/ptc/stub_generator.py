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


def generate_ptc_code(llm_code: str, mode: str = "ipc") -> str:
    if mode == "ipc":
        return IPC_PREAMBLE + "\n" + llm_code
    else:
        from runtime.ptc.sandbox_executor import PTC_PREAMBLE
        return PTC_PREAMBLE + "\n" + llm_code
