# Runtime Runner

This package owns thin orchestration entrypoints that connect contracts across role boundaries.

Current role:
- `Session Signal Runner`: accepts a bounded `session_structure_signal.v1`, runs provider runtime integrity, then runs session admission only when integrity allows it.

The runner package must not become an observer daemon and must not own semantic category, canonical claim, or mailbox mutation decisions.
