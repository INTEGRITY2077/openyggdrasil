# Runtime Capture

`runtime/capture/` converts provider/session observations into bounded decision
artifacts.

## Responsibilities

- check provider runtime integrity before chain admission
- normalize a schema-valid `decision_surface` into a `decision_candidate`
- preserve source references and provider/session identity
- avoid storing whole provider conversations as memory candidates

Provider adapters may supply model-generated candidate text, but canonical
normalization and validation live here.
