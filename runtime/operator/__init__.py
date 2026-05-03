"""
Operator Subpackage — runtime/operator/

14차 Axis 3 S5: Re-export 정리. operator_entrypoint.py의 함수들을 모듈별로 재배치.

Modules:
  producer.py  — run_producer (main entry)
  consumer.py  — run_consumer, _bm25_search_vault
  helpers.py   — deliver_receipt, _update_status, _update_manifest, Q13 utilities
  prune.py     — _handle_prune, _classify_prune_target, _restore_from_archive, _handle_skill_update,
                 _read_last_curation, _days_since, _run_hygiene_check, _run_piggybacked_gardener,
                 hygiene helpers

Public API (from operator_entrypoint.py):
  run_producer(mailbox, vault)
  run_consumer(mailbox, vault)
"""
from .producer import run_producer
from .consumer import run_consumer, _bm25_search_vault
from .helpers import deliver_receipt, _update_status, _update_manifest, _ensure_q13_dirs, _write_context_bundle
from .prune import (
    _handle_prune,
    _classify_prune_target,
    _restore_from_archive,
    _handle_skill_update,
    _read_last_curation,
    _days_since,
    _run_hygiene_check,
    _run_piggybacked_gardener,
    _count_contradiction_chains,
    _count_stale_nodes,
    _drop_curate_intent,
    _drop_prune_intent,
    _write_hygiene_report,
    _write_last_run,
)

__all__ = [
    "run_producer",
    "run_consumer",
    "_bm25_search_vault",
    "deliver_receipt",
    "_update_status",
    "_update_manifest",
    "_ensure_q13_dirs",
    "_write_context_bundle",
    "_handle_prune",
    "_classify_prune_target",
    "_restore_from_archive",
    "_handle_skill_update",
    "_read_last_curation",
    "_days_since",
    "_run_hygiene_check",
    "_run_piggybacked_gardener",
    "_count_contradiction_chains",
    "_count_stale_nodes",
    "_drop_curate_intent",
    "_drop_prune_intent",
    "_write_hygiene_report",
    "_write_last_run",
]
