# Runtime Delivery

`runtime/delivery/` owns Postman, mailbox, and support-bundle delivery.

## Responsibilities

- build bounded `support_bundle.v1` artifacts
- score and package inbox packets
- store session-bound mailbox state
- guard against mailbox contamination and unrelated memory leakage
- finalize delivery handoffs for provider sessions
- keep provider-facing support separate from canonical vault mutation

Delivery does not decide semantic truth. It moves already-bounded support to the
right provider/session inbox.
