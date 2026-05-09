# Runtime Delivery

`runtime/delivery/` owns Postman delivery admission, mailbox work orders,
worker work history, Result Receipt mirroring, and bounded Evidence Pack
delivery. Legacy `support_bundle` names remain where schema or module
compatibility requires them.

## Responsibilities

- build bounded Evidence Pack artifacts (`support_bundle.v1` compatibility)
- accept Provider letters and create mailbox `postman_work_order.v1` rows
- mirror worker results into `worker_work_history.v1`
- score and package inbox packets
- store session-bound mailbox state
- guard against mailbox contamination and unrelated memory leakage
- finalize delivery handoffs for provider sessions
- keep provider-facing support separate from canonical vault mutation

Delivery does not decide semantic truth. Postman moves work and mirrors results;
MS/MF own storage and recall judgment, and Provider owns the user-facing answer.
