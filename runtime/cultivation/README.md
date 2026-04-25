# Runtime Cultivation

This family owns deterministic Seedkeeper preservation plus Gardener-style forest and community maintenance logic.

It also hosts the Phase 5 explicit vault promotion request builder. That builder
records Evaluator and mailbox-delivery gates for later review, but it does not
write canonical vault state.

Phase 5 lifecycle helpers define soft-delete state for promoted/canonical vault
records. They mark records `ACTIVE`, `SUPERSEDED`, or `STALE` with temporal
traceability fields and never authorize physical deletion.

Gardener lifecycle transition request helpers can propose `SUPERSEDED` or
`STALE` transitions for active records. They preserve archive lineage in a typed
preview, require later lifecycle review, and do not write canonical vault state.

Cross-provider conflict quarantine helpers detect same-key contradictory or
ambiguous active records from different providers. They apply an explicit
discounting rule, route the claim to review/fallback, and do not canonicalize
ambiguous memory.

Effort-aware Gardener worthiness helpers gate promotion review on verified
effort metadata and actual effort estimates. They defer low, unknown, or
downgraded effort before review and never write canonical vault state.
