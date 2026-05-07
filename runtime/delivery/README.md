# Runtime Delivery

`runtime/delivery/` owns Delivery Monitor, mailbox, and Evidence Pack delivery.
Legacy Postman/support_bundle names remain only where schema or module
compatibility requires them.

## Responsibilities

- build bounded Evidence Pack artifacts (`support_bundle.v1` compatibility)
- score and package inbox packets
- store session-bound mailbox state
- guard against mailbox contamination and unrelated memory leakage
- finalize delivery handoffs for provider sessions
- keep provider-facing support separate from canonical vault mutation

Delivery does not decide semantic truth. It moves already-bounded support to the
right provider/session inbox.
