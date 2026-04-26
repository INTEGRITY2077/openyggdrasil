# Runtime Cultivation

`runtime/cultivation/` owns memory gardening after a candidate has passed
capture, admission, and evaluation boundaries.

## Responsibilities

- preserve accepted material through Seedkeeper/Nursery-style helpers
- build explicit vault promotion requests without directly writing canonical
  vault state
- propose lifecycle transitions such as `ACTIVE`, `SUPERSEDED`, and `STALE`
- quarantine contradictory cross-provider claims
- normalize provider effort vocabulary and gate worthiness on verified effort
- stage helper output only after worthiness and evidence checks pass
- turn lint/simplicity findings into typed lifecycle proposals

Cultivation is proposal-oriented. It must not silently mutate canonical vault
records or delete history without an explicit lifecycle artifact.
