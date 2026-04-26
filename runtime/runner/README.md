# Runtime Runner

`runtime/runner/` owns thin orchestration and proof entrypoints across runtime
boundaries.

## Responsibilities

- connect provider integrity, session admission, worker chain, mailbox support,
  and fallback paths
- produce typed result artifacts for accepted, rejected, unavailable, declined,
  and fallback outcomes
- run user-like regression scenarios without copying raw provider answers or
  transcripts
- expose live or foreground-equivalent provider proof honestly instead of
  relabeling fallbacks as live support

## Current Entry Points

- `session_signal_runner.py`
- `thin_worker_chain.py`
- `mailbox_support_emission.py`
- `failure_fallback_regression.py`
- `same_session_answer_smoke.py`
- `hermes_live_replay_regression.py`
- `no_credential_prompt_regression.py`
- `real_ux_regression.py`
- `real_ux_regression_summary.py`
- `provider_declined_visibility.py`

Runner code must not become an observer daemon and must not own semantic
category, canonical claim, or mailbox mutation decisions.
