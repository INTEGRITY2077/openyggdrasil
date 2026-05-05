"""
Operator Entrypoint — SKILL이 호출하는 런타임 진입점.

engine.py를 터치하지 않는다. POC에서 검증된 primitive를
runtime/ptc/primitives.py에서 import하여 SKILL 어포던스 아래에서
조합한다.

14차 Axis 3: producer/consumer/prune/helpers → runtime/operator/ 분리 완료.
operator_entrypoint.py는 순수 entrypoint + tests backward-compat re-export만 담당.

Usage (Provider SKILL → subprocess):
    python -m runtime.operator_entrypoint produce --mailbox /path/to/mailbox --vault /path/to/vault
    python -m runtime.operator_entrypoint consume --mailbox /path/to/mailbox --vault /path/to/vault
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from runtime.operator.producer import run_producer
from runtime.operator.consumer import run_consumer

# ─── tests backward-compat re-exports (구현은 runtime/operator/ 아래에 있음) ───

from runtime.operator.helpers import (  # noqa: F401 — tests import from here
    deliver_receipt,
    _update_status,
    _update_manifest,
    _ensure_q13_dirs,
    _write_context_bundle,
)

from runtime.operator.prune import (  # noqa: F401 — tests import from here
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

# ─── consumer BM25 re-export (tests backward-compat) ───
from runtime.operator.consumer import _bm25_search_vault  # noqa: F401


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="openyggdrasil Operator Entrypoint")
    parser.add_argument("mode", choices=["produce", "consume"])
    parser.add_argument("--mailbox", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    args = parser.parse_args()

    if args.mode == "produce":
        run_producer(args.mailbox, args.vault)
    else:
        run_consumer(args.mailbox, args.vault)
