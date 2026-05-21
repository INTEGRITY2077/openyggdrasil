#!/usr/bin/env python3
"""
ygg - openyggdrasil Provider Unit manager

Canonical numbering:
  Provider Unit N = PRO N + MS N + MF N
  PRO N = Provider Lane N
  MS N  = Memory Saver N
  MF N  = Memory Finder N

Usage:
  ygg pro1                     open/recall Provider Lane 1
  ygg pro1 --doctor            check Provider Unit 1 health
  ygg pro1 --cpr               read latest Status Brief for Provider Lane 1
  ygg ms1                      open/recall Memory Saver 1
  ygg mf1                      open/recall Memory Finder 1

  ygg spawn [provider]          reuse or create a Provider Unit memory pair
  ygg spawn --new [provider]    explicitly create the next Provider Unit memory pair
  ygg list                      list memory lanes
  ygg release <ms1|mf1>         release a memory lane
  ygg status [ms1|mf1]          inspect a memory lane

  ygg tell [--stdin|--b64 TEXT] <ms1> <message>
                                send a Save Request to a Memory Saver
  ygg tell --memory-ticket <ms1> <fields>
                                send a structured MemoryTicket Save Request
  ygg ask [--stdin|--b64 TEXT] <mf1> <question>
                                send a Find Request to a Memory Finder
  ygg recall [--stdin|--b64 TEXT] <mf1> <question>
                                send a Find Request asynchronously
  ygg recall --wait <mf1> <question>
                                verification-only bounded Result Receipt wait
  ygg watch <ms1|mf1>           tail the memory lane mailbox
  ygg live <ms1|mf1>            optional MS/MF debug lens; not default Postman path
  ygg flow <ms1|mf1>            optional debug receipt tail; Hermes pane remains primary
  ygg cpr [--json]              read the Provider-bound Status Brief
  ygg cpr --wake-provider       record an internal Provider heartbeat; never writes Provider pane

Compatibility:
  MSN/MFN are the active registry and mailbox ids.
  Legacy OP ids are migration-only source ids and must not be active status evidence.

Registry: ~/.yggdrasil/registry.json
Sessions:  ~/.yggdrasil/sessions/MS{N}/ and ~/.yggdrasil/sessions/MF{N}/
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import base64
from datetime import datetime, timezone
from pathlib import Path

PRIVATE_DEV_ROOT = Path(
    os.environ.get("OY_PRIVATE_DEV", str(Path(__file__).parents[2]))
)
SCRIPTS_DIR = PRIVATE_DEV_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from runtime.delivery.postman_cpr_wakeup import provider_lane_monitor_summary, wake_provider_with_cpr
from runtime.delivery.postman_native_activation import activate_native_lane
from runtime.common.vault_root import resolve_vault_root
from runtime.common.role_aliases import (
    DEFAULT_ACTIVE_WORKER_PAIR,
    LEGACY_OPERATOR_TMUX_SESSION_PATTERN,
)

REGISTRY_DIR = Path.home() / ".yggdrasil"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"
SESSIONS_DIR = REGISTRY_DIR / "sessions"
REPO = Path(os.environ.get("OPENYGGDRASIL_REPO", str(PRIVATE_DEV_ROOT)))
PRIVATE_DEV = PRIVATE_DEV_ROOT
DEFAULT_VAULT_ROOT = resolve_vault_root(workspace_root=PRIVATE_DEV)
PROVIDER_LANE_DIR = REGISTRY_DIR / "provider_lanes"
PROVIDER_PAIR_SESSION = "ygg-pro1"
DEFAULT_PROVIDER_ID = "hermes"
DEFAULT_PROVIDER_PROFILE = "openyggdrasil-provider"
DEFAULT_PROVIDER_COMMAND = "hermes chat --skills openyggdrasil-provider"
DEFAULT_MEMORY_SAVER_COMMAND = "hermes chat --skills openyggdrasil-memory-saver"
DEFAULT_MEMORY_FINDER_COMMAND = "hermes chat --skills openyggdrasil-memory-finder"
NATIVE_PROVIDER_SESSION_UNOBSERVED = "native-provider-session-not-observed"
POSTMAN_CPR_SCHEMA_VERSION = "postman_heartbeat_cpr.v1"
POSTMAN_CPR_PACKET_TYPE = "operator_brief"
LEGACY_PROVIDER_SESSIONS = ("oy-1", "oy-provider")
TMUX_CORE_SESSIONS = {PROVIDER_PAIR_SESSION, "ygg-ms1", "ygg-mf1"}
DEFAULT_ACTIVE_PAIR = DEFAULT_ACTIVE_WORKER_PAIR
TMUX_HYGIENE_OPTIONS = (
    ("set-option", "-g", "history-limit", "20000"),
    ("set-option", "-g", "escape-time", "10"),
    ("set-option", "-g", "status-interval", "5"),
    ("set-option", "-g", "detach-on-destroy", "on"),
    ("set-option", "-g", "remain-on-exit", "off"),
    ("set-window-option", "-g", "aggressive-resize", "on"),
)

def _env_text(name: str) -> str:
    return os.environ.get(name, "").strip()

def _decode_b64_text(value: str) -> str:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
    except Exception as exc:
        print(f"Error: invalid UTF-8 base64 text: {exc}")
        sys.exit(2)

def _default_vault() -> Path:
    return resolve_vault_root(workspace_root=PRIVATE_DEV)

def _shell_quote(value: str | Path) -> str:
    return shlex.quote(str(value))

def _provider_id(default: str | None = None) -> str:
    return _env_text("OY_PROVIDER_ID") or default or DEFAULT_PROVIDER_ID

def _provider_profile(provider_id: str) -> str:
    configured = _env_text("OY_PROVIDER_PROFILE")
    if configured:
        return configured
    if provider_id == "hermes":
        return DEFAULT_PROVIDER_PROFILE
    return f"openyggdrasil-{provider_id}"

def _format_launcher_command(template: str, **values: str) -> str:
    return template.format(
        provider_id=values.get("provider_id", ""),
        provider_profile=values.get("provider_profile", ""),
        provider_session_id=values.get("provider_session_id", ""),
        workspace_root=str(REPO),
        op=values.get("op", ""),
        role=values.get("role", ""),
        mailbox=values.get("mailbox", ""),
        vault=values.get("vault", ""),
    )

def _provider_command(provider_id: str, provider_profile: str, provider_session_id: str) -> str | None:
    template = _env_text("OY_PROVIDER_COMMAND")
    if template:
        return _format_launcher_command(
            template,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        )
    if provider_id == "hermes":
        return DEFAULT_PROVIDER_COMMAND
    return None

def _workflow(role: str, *, now: str, watching: str, creating: str,
              created: str, evidence: str, next_action: str, status: str) -> None:
    """LLM/사용자 컨텍스트에 남길 행동 중심 표면."""
    print(f"[{role} WORKFLOW]")
    print(f"지금 할 일: {now}")
    print(f"보고 있는 것: {watching}")
    print(f"생성할 것: {creating}")
    print(f"방금 만든 것: {created}")
    print(f"근거: {evidence}")
    print(f"다음 행동: {next_action}")
    print(f"상태: {status}")


__all__ = [name for name in globals() if not name.startswith('__')]
