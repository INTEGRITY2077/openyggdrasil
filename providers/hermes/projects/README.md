# Hermes Projects

`providers/hermes/projects/` is a public boundary for Hermes-specific adapter
projects.

No operator harness bundle is published here. Older Hermes-facing orchestration,
mailbox, live-monitor, replay, and proof scripts belong to private development
history or a reviewed runtime migration, not to the public provider package.

## Boundary

Operator-only project bundles are not published in this repository. That
includes credential helpers, transcript capture, private wiki-promotion flows,
live session witnesses, replay harnesses, and raw provider workflow material.

Graphify is not owned by this provider subtree. The provider-neutral Graphify
stack lives at `common/graphify/`.
