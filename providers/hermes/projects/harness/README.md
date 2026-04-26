# Hermes External Harness

This project contains the external single-writer harness for the current Hermes stack.

Its job is to keep canonical knowledge updates out of the Hermes core runtime.

Mailbox contract reference:

- `%HERMES_ROOT%\projects\harness\mailbox.v1.schema.json`
- `%HERMES_ROOT%\policy\README.md`

Mailbox reverse-push POC helpers:

- `%HERMES_ROOT%\projects\harness\mailbox_common.py`
- `%HERMES_ROOT%\projects\harness\emit_push_poc.py`
- `%HERMES_ROOT%\projects\harness\postman_push_once.py`
- `%HERMES_ROOT%\projects\harness\mailbox_select.py`

## Responsibility

- enqueue promotion jobs
- enqueue Graphify rebuild jobs
- serialize canonical writes behind one worker
- record queue and worker events under `%HERMES_ROOT%\ops`

This project does **not** replace:

- Hermes session persistence
- Hermes profiles
- Hermes ACP
- Hermes gateway

## Runtime Artifacts

The worker writes runtime artifacts here:

- `%HERMES_ROOT%\ops\queue\jobs.jsonl`
- `%HERMES_ROOT%\ops\queue\worker-events.jsonl`
- `%HERMES_ROOT%\ops\locks\worker.lock`
- `%HERMES_ROOT%\ops\locks\promotion.lock`
- `%HERMES_ROOT%\ops\locks\graph.lock`

The mailbox reverse-push POC writes runtime artifacts here:

- `%HERMES_ROOT%\ops\mailbox\messages.jsonl`
- `%HERMES_ROOT%\ops\mailbox\claims.jsonl`
- `%HERMES_ROOT%\ops\mailbox\latest-status.json`
- `%HERMES_ROOT%\ops\mailbox\inbox\...`

The plugin-plane dedicated logger writes here:

- `%HERMES_ROOT%\ops\plugin-logger\plugin-events.jsonl`

These paths are already ignored by the canonical repo.

## Enqueue One Promotion Job

```powershell
py -3 %HERMES_ROOT%\projects\harness\enqueue_promotion.py `
  --profile wiki `
  --session-id 20260421_182110_add6a4
```

## Enqueue One Promotion Job And Chain Graphify

```powershell
py -3 %HERMES_ROOT%\projects\harness\enqueue_promotion.py `
  --profile wiki `
  --session-id 20260421_182110_add6a4 `
  --chain-graph
```

## Enqueue One Graph Rebuild

```powershell
py -3 %HERMES_ROOT%\projects\harness\enqueue_graph_rebuild.py
```

## Replay One Failed Job

```powershell
py -3 %HERMES_ROOT%\projects\harness\replay_failed_job.py `
  --job-id 43833a4a52da481e8745d25ce89f0aa8 `
  --max-replay-depth 2
```

## Discover Unpromoted Sessions

```powershell
py -3 %HERMES_ROOT%\projects\harness\discover_sessions.py `
  --profiles wiki graph `
  --limit 1 `
  --chain-graph
```

The discovery path scans official Hermes `sessions/*.json` artifacts and only enqueues
promotion for sessions that do not already have a canonical transcript.

Verified flow:

- discover unpromoted official session
- enqueue `promotion`
- worker processes `promotion`
- worker enqueues chained `graph_rebuild`
- worker processes chained `graph_rebuild`

Quality gate:

- skip sessions that already have a canonical transcript
- skip sessions that already have an active promotion job
- skip obvious smoke/test prompts such as `Say only ...`, `WIKI_OK`, `GRAPH_OK`
- skip sessions that hit the tool-call iteration limit
- skip sessions whose final assistant answer is shorter than the configured threshold
- skip sessions whose final assistant answer matches failure-style fallback language

## Dedup Behavior

- enqueue paths are serialized behind a queue lock
- active duplicate jobs are skipped during normal enqueue
- the scripts print `SKIPPED_DUPLICATE <job_id>` when that happens
- replay is an explicit operator action and intentionally creates a new job
- replay only accepts jobs whose latest status is `failed`
- replay preserves `parent_question_id`, `replay_root_job_id`, and bounded `replay_depth`
- replay depth is capped so failed jobs cannot be re-enqueued forever

## Force Re-enqueue

```powershell
py -3 %HERMES_ROOT%\projects\harness\enqueue_graph_rebuild.py --force
```

## Run The Worker Once

```powershell
py -3 %HERMES_ROOT%\projects\harness\run_worker.py --once
```

## Emit One Push-Ready Packet

```powershell
py -3 %HERMES_ROOT%\projects\harness\emit_push_poc.py `
  --profile wiki `
  --session-id push-poc-20260421-2230 `
  --topic "mailbox reverse push"
```

## Deliver Push-Ready Packets Once

```powershell
py -3 %HERMES_ROOT%\projects\harness\postman_push_once.py `
  --profile wiki `
  --session-id push-poc-20260421-2230 `
  --limit 1
```

## Select Delivered Inbox Packets For Hermes Preflight

```powershell
py -3 %HERMES_ROOT%\projects\harness\mailbox_select.py `
  --profile wiki `
  --session-id push-poc-20260421-2230 `
  --query "Can you use the reverse push mailbox hint before answering?" `
  --top-k 1
```

## Current POC Scope

- single host
- one worker process at a time
- file-based queue
- file-based locks
- promotion and graph rebuild only
- mailbox reverse-push POC into a Hermes-consumable inbox

## Notes

- `promotion` uses the existing canonical script under `projects/wiki-promotion`
- `graph_rebuild` uses the existing canonical wrapper under `common/graphify-poc`
- `graph_rebuild` runs inside WSL `ubuntu-agent` with `%GRAPHIFY_SANDBOX_ROOT%\.venv-wsl`
- enqueue operations use a queue lock so duplicate checks are safe under concurrent requests
- discovery only considers sessions without an existing canonical transcript
- discovery applies a conservative quality gate before enqueue
- the queue is append-only; completion and failure are derived from `worker-events.jsonl`
- mailbox `push_ready` packets can be reverse-delivered by the postman into `ops/mailbox/inbox`
- this proves custom reverse delivery into a Hermes-consumable inbox, not native live interruption of an already-running Hermes turn
- plugin-plane answer-shaping events, including final answer-edge render events, are logged separately from subagent telemetry under `ops/plugin-logger`
