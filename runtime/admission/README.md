# Runtime Admission

`runtime/admission/` decides whether a captured provider/session signal is
usable by the memory chain.

## Responsibilities

- validate bounded session signals before they enter the chain
- classify accepted, rejected, deferred, and review-required surfaces
- emit Amundsen/Nursery handoff artifacts when a candidate needs routing
- resolve source references without copying provider raw material

Admission does not promote vault records and does not deliver mailbox support.
