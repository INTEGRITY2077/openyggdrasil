# Runtime Capture

This package owns provider-neutral decision capture roles.

Current role:
- `Decision Distiller`: converts a schema-valid `decision_surface` into a schema-valid `decision_candidate`.
- `Provider Runtime Integrity`: checks provider-runtime repair/interruption state before a `session_structure_signal` reaches admission.

Provider adapters may supply the high-reasoning renderer, but canonical candidate normalization and validation live here.
