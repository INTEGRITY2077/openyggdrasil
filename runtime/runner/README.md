# Runtime Runner

This package owns thin orchestration entrypoints that connect contracts across role boundaries.

Current role:
- `Session Signal Runner`: accepts a bounded `session_structure_signal.v1`, runs provider runtime integrity, then runs session admission only when integrity allows it.
- `Thin Worker Chain`: turns an accepted runner result into deterministic Distiller/Evaluator/Amundsen/Gardener/Map Maker/Postman boundary artifacts without running full role services.
- `Mailbox Support Emission`: turns a completed thin chain result into a guarded `support_bundle.v1` session inbox packet.
- `Failure Fallback Regression`: proves known failure modes return typed fallback/quarantine/reject results instead of provider-facing uncaught exceptions.
- `Same Session Answer Smoke`: proves a foreground-equivalent provider answer consumes the delivered session support bundle while an unrelated decoy does not.
- `Hermes Live Replay Regression`: probes whether the checked-in Hermes live surface is available, then runs live or foreground-equivalent replay proof for source shortcut consumption and decoy rejection.
- `No Credential Prompt Regression`: scans Phase 4 runtime-facing lease/request/result surfaces and fails if OpenYggdrasil emits API key, OAuth, credential, or stored-credential prompts.
- `Real UX Regression`: owns Phase 2 deterministic user-like accepted decision, correction/supersession, boundary transition, context-pressure, irrelevant decoy, and follow-up retrieval scenarios before live-provider polish.
- `Real UX Regression Summary`: summarizes Phase 2 result artifacts without copying provider answers, raw transcripts, or provider raw sessions.
- `Provider Declined Visibility`: exposes declined reasoning lease results as typed runner-visible states instead of collapsing them into generic failures.

Current contract:
- `session_signal_runner_result.v1`: typed entrypoint result consumed by the thin worker chain.
- `thin_worker_chain_result.v1`: typed chain result consumed by mailbox/support emission.
- `mailbox_support_result.v1`: typed mailbox/support emission result consumed by same-session answer smoke.
- `failure_fallback_regression_result.v1`: typed S2 regression summary for missing provider background reasoning, missing Graphify snapshot, stale mailbox packet, and unresolved source ref.
- `same_session_answer_smoke_result.v1`: typed R4 smoke result for same-session support consumption and decoy rejection.
- `hermes_live_replay_regression_result.v1`: typed P1.C1 result that records live surface availability, fallback classification, source shortcut presence, and decoy rejection.
- `no_credential_prompt_regression_result.v1`: typed Phase 4 regression result proving runtime surfaces do not emit credential/API/OAuth prompts.
- `real_ux_regression_result.v1`: typed Phase 2 result for accepted decision UX, correction/supersession UX, boundary transition UX, context-pressure typed defer, irrelevant decoy rejection, follow-up retrieval, support delivery, and source/provenance answer shortcut proof.
- `real_ux_regression_summary.v1`: typed Phase 2 summary for result artifact inspection without answer text or raw transcript payloads.
- `provider_declined_runner_visibility.v1`: typed Phase 4 runner visibility result for provider-declined reasoning leases and related non-completed states.

The runner package must not become an observer daemon and must not own semantic category, canonical claim, or mailbox mutation decisions.
