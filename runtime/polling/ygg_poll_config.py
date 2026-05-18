from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from runtime.common.role_aliases import (
    legacy_mailbox_name_for_mode,
    worker_short_label_for_mode,
)


@dataclass(frozen=True)
class YggPollConfig:
    mode: str
    mailbox: Path
    vault: Path
    poll_interval: int
    mailbox_key: str
    role_label: str
    receipt_name: str
    intent_name: str
    tmux_target: str
    trigger_timeout: int
    native_goal_mode: bool
    native_goal_action_loop: bool
    native_goal_multi_step: bool
    native_goal_stage_goals: bool
    worker_owned_native_loop: bool
    enable_legacy_ralph_prompts: bool


def _env_flag(env: Mapping[str, str], name: str, *, default: str = "0") -> bool:
    return str(env.get(name, default)).strip() == "1"


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _normalized_path_text(path: str | Path) -> str:
    value = str(path).replace("\\", "/").lower()
    if len(value) >= 3 and value[1:3] == ":/":
        value = f"/mnt/{value[0]}{value[2:]}"
    return value.rstrip("/")


def _is_public_runtime_vault(vault: str | Path, repo_root: Path) -> bool:
    vault_text = _normalized_path_text(vault)
    candidates = (
        repo_root / "vault",
        repo_root.parent / "openyggdrasil" / "vault",
    )
    for candidate in candidates:
        candidate_text = _normalized_path_text(candidate)
        if vault_text == candidate_text or vault_text.startswith(candidate_text + "/"):
            return True
    private_repo_marker = "openyggdrasil" + "-private-dev"
    return (
        "/0_project/openyggdrasil/vault" in vault_text
        and f"/{private_repo_marker}/" not in vault_text
    )


def build_ygg_poll_config(
    *,
    mode: str,
    mailbox: str | Path,
    vault: str | Path,
    env: Mapping[str, str],
    poll_interval: int = 3,
) -> YggPollConfig:
    normalized_mode = "produce" if str(mode or "").strip().lower() == "produce" else "consume"
    repo_root = Path(__file__).resolve().parents[2]
    if (
        _is_public_runtime_vault(vault, repo_root)
        and not _env_flag(env, "OY_ALLOW_PUBLIC_RUNTIME_VAULT")
    ):
        raise ValueError("public_runtime_vault_forbidden")
    enable_legacy_ralph_prompts = _env_flag(env, "OY_ENABLE_LEGACY_RALPH_PROMPTS")
    native_goal_mode = _env_flag(env, "OY_OP_NATIVE_GOAL")
    native_goal_action_loop = _env_flag(env, "OY_OP_NATIVE_GOAL_ACTION_LOOP")
    native_goal_multi_step = _env_flag(env, "OY_OP_NATIVE_GOAL_MULTI_STEP")
    native_goal_stage_goals = _env_flag(env, "OY_OP_NATIVE_GOAL_STAGE_GOALS")
    if not enable_legacy_ralph_prompts:
        native_goal_mode = False
        native_goal_action_loop = False
        native_goal_multi_step = False
        native_goal_stage_goals = False
    return YggPollConfig(
        mode=normalized_mode,
        mailbox=Path(mailbox),
        vault=Path(vault),
        poll_interval=poll_interval,
        mailbox_key=legacy_mailbox_name_for_mode(normalized_mode),
        role_label=worker_short_label_for_mode(normalized_mode),
        receipt_name="receipts.jsonl" if normalized_mode == "produce" else "query_receipts.jsonl",
        intent_name="intents.jsonl" if normalized_mode == "produce" else "queries.jsonl",
        tmux_target="ygg-ms1:1" if normalized_mode == "produce" else "ygg-mf1:1",
        trigger_timeout=300,
        native_goal_mode=native_goal_mode,
        native_goal_action_loop=native_goal_action_loop,
        native_goal_multi_step=native_goal_multi_step,
        native_goal_stage_goals=native_goal_stage_goals,
        worker_owned_native_loop=_env_flag(env, "OY_OP_WORKER_OWNED_NATIVE_LOOP"),
        enable_legacy_ralph_prompts=enable_legacy_ralph_prompts,
    )


__all__ = ["YggPollConfig", "build_ygg_poll_config"]
