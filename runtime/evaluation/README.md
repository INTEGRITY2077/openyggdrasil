# Runtime Evaluation

This family will own durable candidate worthiness and evaluation logic.

Phase 3 Evaluator scope is deterministic prefilter only. It may accept a
candidate for Amundsen, reject it, or defer it. If a candidate requires
high-reasoning fuel, Evaluator emits a typed Phase 4 handoff recommendation
and must not request credentials, call a provider, or pretend the high-
reasoning work was completed.

Evaluator may also mark vault-promotion readiness for Phase 5, but it never
emits a vault promotion request and never mutates vault state. Phase 5 Postman
owns promotion request emission after mailbox delivery.
