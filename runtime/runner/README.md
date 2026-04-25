# Runtime Runner

This package owns thin orchestration entrypoints that connect contracts across role boundaries.

Current role:
- `Session Signal Runner`: accepts a bounded `session_structure_signal.v1`, runs provider runtime integrity, then runs session admission only when integrity allows it.
- `Thin Worker Chain`: turns an accepted runner result into deterministic Distiller/Evaluator/Amundsen/Gardener/Map Maker/Postman boundary artifacts without running full role services.
- `Mailbox Support Emission`: turns a completed thin chain result into a guarded `support_bundle.v1` session inbox packet.

Current contract:
- `session_signal_runner_result.v1`: typed entrypoint result consumed by the thin worker chain.
- `thin_worker_chain_result.v1`: typed chain result consumed by mailbox/support emission.
- `mailbox_support_result.v1`: typed mailbox/support emission result consumed by same-session answer smoke.

The runner package must not become an observer daemon and must not own semantic category, canonical claim, or mailbox mutation decisions.
