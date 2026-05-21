#!/usr/bin/env python3
"""ygg CLI parser and command dispatcher."""
from __future__ import annotations

import re
import sys

from runtime.cli.ygg_config import _decode_b64_text, _provider_id
from runtime.cli.ygg_compaction import cmd_compact_check
from runtime.cli.ygg_cpr import cmd_cpr
from runtime.cli.ygg_flow import cmd_flow, cmd_live, cmd_receipt, cmd_watch
from runtime.cli.ygg_memory_lanes import (
    cmd_ask,
    cmd_dev,
    cmd_list,
    cmd_op,
    cmd_provider_command,
    cmd_recall,
    cmd_release,
    cmd_spawn,
    cmd_status,
    cmd_tell,
)
from runtime.cli.ygg_registry import (
    _load_registry,
    _op_label,
    _resolve_op,
    cmd_provider_lane_doctor,
    cmd_tmux_doctor,
)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        print("Usage: ygg <cmd> [args]")
        print("  ygg pro1                  Provider Lane 1 open/recall")
        print("  ygg pro1 --doctor         Provider Unit 1 healthcheck")
        print("  ygg ms1                   Memory Saver 1 open/recall")
        print("  ygg mf1                   Memory Finder 1 open/recall")
        print("  ygg spawn [provider]       reuse or create a Provider Unit memory pair")
        print("  ygg spawn --new [provider] create the next Provider Unit memory pair")
        print("  ygg list                   list memory lanes")
        print("  ygg tell [--stdin|--b64 TEXT] <ms1> <message> Save Request to a Memory Saver")
        print("  ygg tell --memory-ticket <ms1> <fields> structured Save Request")
        print("  ygg ask [--stdin|--b64 TEXT] <mf1> <question> Find Request to a Memory Finder")
        print("  ygg recall [--ptc] [--json] [--stdin|--b64 TEXT] <mf1> <question>")
        print("                              async Provider recall via Memory Finder")
        print("  ygg recall --wait [--timeout N] <mf1> <question>")
        print("                              verification-only; Provider sessions downgrade to async unless explicitly allowed")
        print("  ygg doctor                 Provider Unit 1 healthcheck")
        print("  ygg cpr [--json]           Provider-bound Status Brief check")
        print("  ygg cpr --wake-provider    record an internal Provider heartbeat")
        print("  ygg cpr --wake-provider --inject-visible")
        print("                              dev fallback: type one bounded prompt into PRO1")
        print("  ygg compact-check [--json] observe native preflight compression and write pointer memento only when proven")
        print("  ygg dev                    compatibility alias for ygg pro1")
        print("  ygg dev --doctor           compatibility alias for ygg pro1 --doctor")
        print("  ygg watch <ms1|mf1>        tail memory lane mailbox")
        print("  ygg live <ms1|mf1>         optional MS/MF debug lens; not default Postman path")
        print("  ygg flow <ms1|mf1>         optional debug receipt tail; Hermes pane remains primary")
        print("  ygg receipt <mail_id>      check mail_id handling state")
        print("  ygg tmux                   tmux witness hygiene/status")
        print("  ygg status [ms1|mf1]       memory lane status")
        print("  ygg release <ms1|mf1>      release a memory lane")
        print("  numbering: Provider Unit N = PRO N + MS N + MF N")
        print("  note: tmux names are internal evidence ids; use ygg pro1 / ygg ms1 / ygg mf1")
        print("  provider env: OY_PROVIDER_ID, OY_PROVIDER_PROFILE, OY_PROVIDER_COMMAND")
        print("  memory env: OY_MEMORY_SAVER_COMMAND/OY_MS_COMMAND, OY_MEMORY_FINDER_COMMAND/OY_MF_COMMAND")
        print("  vault env: OY_VAULT (default: ~/.yggdrasil/vault)")
        print("  templates may use: {provider_id}, {provider_profile}, {provider_session_id}, {workspace_root}, {role}, {mailbox}, {vault}")
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    cmd = sys.argv[1]

    provider_match = re.match(r'^(pro|provider)(\d+)$', cmd, re.IGNORECASE)
    if provider_match:
        provider_lane = provider_match.group(2)
        if provider_lane != "1":
            print("Error: only ygg pro1 is defined. Do not auto-create pro2/pro3 lanes.")
            sys.exit(1)
        cmd_provider_command(sys.argv[2:])
    elif cmd == "doctor":
        if len(sys.argv) > 2:
            print("Usage: ygg doctor")
            sys.exit(1)
        cmd_provider_lane_doctor()
    elif cmd == "cpr":
        cmd_cpr(sys.argv[2:])
    elif cmd == "compact-check":
        cmd_compact_check(sys.argv[2:])
    elif cmd == "spawn":
        args = sys.argv[2:]
        force_new = False
        if args and args[0] == "--new":
            force_new = True
            args = args[1:]
        provider = args[0] if args else _provider_id()
        cmd_spawn(provider, force_new=force_new)
    elif cmd == "list":
        cmd_list()
    elif cmd == "tell":
        use_ptc = False
        memory_ticket = False
        read_stdin = False
        b64_text = None
        args = sys.argv[2:]
        while args and args[0].startswith("--"):
            if args[0] == "--ptc":
                use_ptc = True
                args = args[1:]
            elif args[0] == "--memory-ticket":
                memory_ticket = True
                args = args[1:]
            elif args[0] == "--stdin":
                read_stdin = True
                args = args[1:]
            elif args[0] == "--b64" and len(args) >= 2:
                b64_text = args[1]
                args = args[2:]
            else:
                print("Usage: ygg tell [--ptc|--memory-ticket] [--stdin|--b64 TEXT] <ms1> [message]")
                sys.exit(1)
        if read_stdin and b64_text is not None:
            print("Usage: ygg tell [--ptc|--memory-ticket] [--stdin|--b64 TEXT] <ms1> [message]")
            sys.exit(1)
        if len(args) < 1 or (not read_stdin and b64_text is None and len(args) < 2):
            print("Usage: ygg tell [--ptc|--memory-ticket] [--stdin|--b64 TEXT] <ms1> [message]")
            sys.exit(1)
        message = (
            _decode_b64_text(b64_text)
            if b64_text is not None
            else sys.stdin.read()
            if read_stdin
            else " ".join(args[1:])
        )
        cmd_tell(args[0], message, use_ptc, memory_ticket)
    elif cmd == "ask":
        use_ptc = False
        read_stdin = False
        b64_text = None
        args = sys.argv[2:]
        while args and args[0].startswith("--"):
            if args[0] == "--ptc":
                use_ptc = True
                args = args[1:]
            elif args[0] == "--stdin":
                read_stdin = True
                args = args[1:]
            elif args[0] == "--b64" and len(args) >= 2:
                b64_text = args[1]
                args = args[2:]
            else:
                print("Usage: ygg ask [--ptc] [--stdin|--b64 TEXT] <mf1> [question]")
                sys.exit(1)
        if read_stdin and b64_text is not None:
            print("Usage: ygg ask [--ptc] [--stdin|--b64 TEXT] <mf1> [question]")
            sys.exit(1)
        if len(args) < 1 or (not read_stdin and b64_text is None and len(args) < 2):
            print("Usage: ygg ask [--ptc] [--stdin|--b64 TEXT] <mf1> [question]")
            sys.exit(1)
        question = (
            _decode_b64_text(b64_text)
            if b64_text is not None
            else sys.stdin.read()
            if read_stdin
            else " ".join(args[1:])
        )
        cmd_ask(args[0], question, use_ptc)
    elif cmd == "recall":
        use_ptc = False
        json_mode = False
        timeout_seconds = 75.0
        wait_for_receipt = False
        read_stdin = False
        b64_text = None
        args = sys.argv[2:]
        while args and args[0].startswith("--"):
            if args[0] == "--ptc":
                use_ptc = True
                args = args[1:]
            elif args[0] == "--json":
                json_mode = True
                args = args[1:]
            elif args[0] == "--wait":
                wait_for_receipt = True
                args = args[1:]
            elif args[0] == "--stdin":
                read_stdin = True
                args = args[1:]
            elif args[0] == "--b64" and len(args) >= 2:
                b64_text = args[1]
                args = args[2:]
            elif args[0] == "--timeout" and len(args) >= 2:
                try:
                    timeout_seconds = float(args[1])
                except ValueError:
                    print("Usage: ygg recall [--ptc] [--json] [--wait] [--stdin|--b64 TEXT] [--timeout N] <mf1> [question]")
                    sys.exit(1)
                wait_for_receipt = True
                args = args[2:]
            else:
                print("Usage: ygg recall [--ptc] [--json] [--wait] [--stdin|--b64 TEXT] [--timeout N] <mf1> [question]")
                sys.exit(1)
        if read_stdin and b64_text is not None:
            print("Usage: ygg recall [--ptc] [--json] [--wait] [--stdin|--b64 TEXT] [--timeout N] <mf1> [question]")
            sys.exit(1)
        if len(args) < 1 or (not read_stdin and b64_text is None and len(args) < 2):
            print("Usage: ygg recall [--ptc] [--json] [--wait] [--stdin|--b64 TEXT] [--timeout N] <mf1> [question]")
            sys.exit(1)
        question = (
            _decode_b64_text(b64_text)
            if b64_text is not None
            else sys.stdin.read()
            if read_stdin
            else " ".join(args[1:])
        )
        cmd_recall(
            args[0],
            question,
            use_ptc=use_ptc,
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
            wait_for_receipt=wait_for_receipt,
        )
    elif cmd == "dev":
        cmd_dev(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "watch":
        cmd_watch(sys.argv[2] if len(sys.argv) > 2 else "ms1")
    elif cmd == "live":
        cmd_live(sys.argv[2] if len(sys.argv) > 2 else "ms1")
    elif cmd == "flow":
        cmd_flow(sys.argv[2] if len(sys.argv) > 2 else "ms1")
    elif cmd == "receipt":
        if len(sys.argv) < 3:
            print("Usage: ygg receipt <mail_id>")
            sys.exit(1)
        cmd_receipt(sys.argv[2])
    elif cmd == "tmux":
        cmd_tmux_doctor()
    elif cmd == "release":
        cmd_release(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "status":
        cmd_status(sys.argv[2] if len(sys.argv) > 2 else "ms1")
    else:
        # Canonical memory-lane commands are msN/mfN. Older aliases are not product-facing commands.
        if re.match(r'^\d+$', cmd):
            print("Error: bare numeric commands are ambiguous. Use 'ygg pro1' for Provider, 'ygg ms1' for Memory Saver 1, or 'ygg mf1' for Memory Finder 1.")
            sys.exit(1)
        if re.match(r'^(op|OP)\d+$', cmd, re.IGNORECASE):
            print("Error: legacy memory-lane alias is not a user command. Use 'ygg ms1' or 'ygg mf1'.")
            sys.exit(1)
        m = re.match(r'^(ms|MS|mf|MF)(\d+)$', cmd, re.IGNORECASE)
        if m:
            op = _resolve_op(cmd)
            reg = _load_registry()
            if op not in reg:
                print(f"Error: {_op_label(op)} not registered. Run 'ygg spawn' first.")
                sys.exit(1)
            if len(sys.argv) > 2:
                if sys.argv[2:] in (["--doctor"], ["--status"]):
                    cmd_status(op)
                    return
                msg = " ".join(sys.argv[2:])
                if reg[op]["type"] == "producer":
                    cmd_tell(op, msg)
                else:
                    cmd_ask(op, msg)
            else:
                cmd_op(op)
        else:
            print(f"Unknown: {cmd}")
            sys.exit(1)

if __name__ == "__main__":
    main()
