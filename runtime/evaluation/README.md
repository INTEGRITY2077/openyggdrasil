# Runtime Evaluation

`runtime/evaluation/` decides whether captured candidates are worth continued
processing.

## Responsibilities

- run deterministic prefilter and evaluator verdict helpers
- mark promotion readiness without writing canonical vault state
- emit Amundsen handoff artifacts for routed candidates
- produce chain health scorecards
- defer high-reasoning surfaces to typed Reasoning Lease planning instead of
  pretending the work completed

Evaluation must not request credentials, call provider APIs directly, or mutate
vault records.
