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
import os
import sys
from pathlib import Path


def _bootstrap_runtime_package_for_direct_script() -> None:
    if __package__:
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runtime_dir = script_dir
    while os.path.basename(runtime_dir) != "runtime":
        parent = os.path.dirname(runtime_dir)
        if parent == runtime_dir:
            return
        runtime_dir = parent
    project_root = os.path.dirname(runtime_dir)
    normalized_runtime_dir = os.path.normcase(os.path.abspath(runtime_dir))
    normalized_project_root = os.path.normcase(os.path.abspath(project_root))
    sys.path[:] = [
        entry
        for entry in sys.path
        if os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_runtime_dir
    ]
    if all(
        os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_project_root
        for entry in sys.path
    ):
        sys.path[:0] = [project_root]


_bootstrap_runtime_package_for_direct_script()


def _early_arg_value(flag: str) -> str | None:
    try:
        index = sys.argv.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(sys.argv):
        return None
    return sys.argv[index + 1]


def _configure_runtime_state_before_import() -> None:
    vault_arg = _early_arg_value("--vault")
    mailbox_arg = _early_arg_value("--mailbox")
    if not vault_arg:
        return
    vault = Path(vault_arg).expanduser()
    lane = Path(mailbox_arg).name if mailbox_arg else "entrypoint"
    os.environ.setdefault("OPENYGGDRASIL_WORKSPACE_ROOT", str(vault.parent))
    os.environ.setdefault("OPENYGGDRASIL_RUNTIME_STATE_ROOT", str(vault.parent / "runtime_state" / lane))


_configure_runtime_state_before_import()


def _runtime_state_root_for_entrypoint(mode: str, mailbox: Path, vault: Path) -> Path:
    lane = mailbox.name or ("MS1" if mode == "produce" else "MF1")
    return vault.parent / "runtime_state" / lane


def _configure_runtime_state_for_entrypoint(mode: str, mailbox: Path, vault: Path) -> None:
    os.environ.setdefault(
        "OPENYGGDRASIL_RUNTIME_STATE_ROOT",
        str(_runtime_state_root_for_entrypoint(mode, mailbox, vault)),
    )
    os.environ.setdefault("OPENYGGDRASIL_WORKSPACE_ROOT", str(vault.parent))


def _allow_missing_vault_root() -> bool:
    return os.environ.get("OY_ALLOW_MISSING_VAULT_ROOT", "").strip() == "1"


def _require_existing_vault_root(vault: Path) -> None:
    if vault.exists():
        return
    if _allow_missing_vault_root():
        return
    raise FileNotFoundError(
        "openyggdrasil vault root does not exist; set OPENYGGDRASIL_VAULT_ROOT/OY_VAULT "
        "to the active vault, or set OY_ALLOW_MISSING_VAULT_ROOT=1 for an explicit bootstrap run"
    )


def run_producer(mailbox: Path, vault: Path, target_mail_id: str | None = None) -> None:
    _require_existing_vault_root(vault)
    _configure_runtime_state_for_entrypoint("produce", mailbox, vault)
    from runtime.operator.producer import run_producer as _run_producer

    _run_producer(mailbox, vault, target_mail_id=target_mail_id)


def run_consumer(mailbox: Path, vault: Path, target_mail_id: str | None = None) -> None:
    _require_existing_vault_root(vault)
    _configure_runtime_state_for_entrypoint("consume", mailbox, vault)
    from runtime.operator.consumer import run_consumer as _run_consumer

    _run_consumer(mailbox, vault, target_mail_id=target_mail_id)

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
def _bm25_search_vault(*args, **kwargs):  # noqa: ANN002, ANN003
    from runtime.operator.consumer import _bm25_search_vault as _impl

    return _impl(*args, **kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="openyggdrasil Operator Entrypoint")
    parser.add_argument("mode", choices=["produce", "consume"])
    parser.add_argument("--mailbox", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--mail-id", default=None, help="Optional single mailbox mail_id to process")
    args = parser.parse_args()

    _configure_runtime_state_for_entrypoint(args.mode, args.mailbox, args.vault)
    if args.mode == "produce":
        run_producer(args.mailbox, args.vault, target_mail_id=args.mail_id)
    else:
        run_consumer(args.mailbox, args.vault, target_mail_id=args.mail_id)
