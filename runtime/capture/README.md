# Runtime Capture

This package owns provider-neutral decision capture roles.

Current role:
- `Decision Distiller`: converts a schema-valid `decision_surface` into a schema-valid `decision_candidate`.

Provider adapters may supply the high-reasoning renderer, but canonical candidate normalization and validation live here.
