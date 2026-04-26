# Hermes Hooks Boundary

This directory is a public documentation anchor for Hermes hook integration.

Hook implementations and runtime copies are provider-local. Public OpenYggdrasil
code must not depend on untracked hook files being present here.

## Rule

- Keep public hook contracts and behavior summaries here only when they are safe
  to publish.
- Keep operator-specific hook files, local runtime state, and provider raw
  output outside the public repository.
