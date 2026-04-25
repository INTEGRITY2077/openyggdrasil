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
