"""
Operator Subpackage — runtime/operator/

14차 Axis 3 S5: Re-export 정리. operator_entrypoint.py의 함수들을 모듈별로 재배치.

Modules:
  producer.py  — run_producer (main entry)
  consumer.py  — run_consumer, _bm25_search_vault
  helpers.py   — deliver_receipt, _update_status, _update_manifest, Q13 utilities
  prune.py     — _handle_prune, _classify_prune_target, _restore_from_archive, _handle_skill_update

Public API (from operator_entrypoint.py):
  run_producer(mailbox, vault)
  run_consumer(mailbox, vault)
"""
from .consumer import run_consumer, _bm25_search_vault
from .helpers import deliver_receipt, _update_status, _update_manifest, _ensure_q13_dirs, _write_context_bundle

__all__ = [
    "run_consumer",
    "_bm25_search_vault",
    "deliver_receipt",
    "_update_status",
    "_update_manifest",
    "_ensure_q13_dirs",
    "_write_context_bundle",
]
