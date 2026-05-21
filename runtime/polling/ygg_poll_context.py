#!/usr/bin/env python3
"""
Optional MS/MF delivery debug lens for producer/consumer mailboxes.

The default product path is Provider -> Postman mailbox routing -> MS/MF worker loop. This
module remains as a private proof/debug lens and must not be treated as the
owner of delivery, wakeup, or worker goal progression.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from runtime.delivery.tmux_lane_adapter import paste_text_enter
from runtime.polling.live_delivery_state import (
    append_goal_log,
    append_live_operator_log,
    append_native_goal_log,
    check_live_events,
    delivered_live_ids,
    mark_live_delivered,
    read_live_jsonl,
    receipt_for_mail_id,
)
from runtime.polling.ptc_trigger_wakeup import (
    build_ptc_trigger_prompt,
    check_ptc_intents,
    prepare_ptc_trigger,
)
from runtime.polling.ygg_poll_config import build_ygg_poll_config

CONFIG = build_ygg_poll_config(
    mode=sys.argv[1],
    mailbox=Path(sys.argv[2]),
    vault=Path(sys.argv[3]),
    env=os.environ,
)
MODE = CONFIG.mode
MAILBOX = CONFIG.mailbox
VAULT = CONFIG.vault
POLL_INTERVAL = CONFIG.poll_interval

op_type = CONFIG.mailbox_key
role = CONFIG.role_label
receipt_name = CONFIG.receipt_name
intent_name = CONFIG.intent_name
tmux_target = CONFIG.tmux_target
TRIGGER_TIMEOUT = CONFIG.trigger_timeout
NATIVE_GOAL_MODE = CONFIG.native_goal_mode
NATIVE_GOAL_ACTION_LOOP = CONFIG.native_goal_action_loop
NATIVE_GOAL_MULTI_STEP = CONFIG.native_goal_multi_step
NATIVE_GOAL_STAGE_GOALS = CONFIG.native_goal_stage_goals
WORKER_OWNED_NATIVE_LOOP = CONFIG.worker_owned_native_loop
ENABLE_LEGACY_RALPH_PROMPTS = CONFIG.enable_legacy_ralph_prompts
REPO_ROOT = Path(os.environ.get("OPENYGGDRASIL_REPO", str(Path(__file__).resolve().parents[2])))

def _shell_quote(value: str | Path) -> str:
    return shlex.quote(str(value))

def _workflow(now: str, watching: str, creating: str, created: str,
              evidence: str, next_action: str, status: str) -> None:
    if WORKER_OWNED_NATIVE_LOOP and (
        "PTC intent" in now
        or "ptc_trigger" in watching
        or "ptc_trigger" in creating
        or "ptc_trigger" in created
        or "ptc_trigger" in evidence
    ):
        return
    if WORKER_OWNED_NATIVE_LOOP:
        replacements = {
            str(MAILBOX): "worker mailbox",
            str(VAULT): "private proof vault",
            str(MAILBOX / intent_name): "worker intent ledger",
            str(MAILBOX / receipt_name): "worker receipt ledger",
        }
        for old, new in replacements.items():
            watching = watching.replace(old, new)
            evidence = evidence.replace(old, new)
            created = created.replace(old, new)
    print(f"[{role} WORKFLOW]", flush=True)
    print(f"now: {now}", flush=True)
    print(f"watching: {watching}", flush=True)
    print(f"creating: {creating}", flush=True)
    print(f"created: {created}", flush=True)
    print(f"evidence: {evidence}", flush=True)
    print(f"next_action: {next_action}", flush=True)
    print(f"status: {status}", flush=True)


__all__ = [name for name in globals() if not name.startswith('__')]
