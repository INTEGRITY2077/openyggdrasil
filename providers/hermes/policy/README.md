# Hermes Policy

This directory is now a public pointer, not the full policy corpus.

## Role
- keep a stable public path for provider policy references
- point operators to the local-only documentation workspace
- avoid shipping the full internal policy tree in the public repo

## Local Documentation Root
- `%OPENYGGDRASIL_ROOT%\\doc\\providers\\hermes\\policy`

That local `doc/` tree is intentionally gitignored and may contain:
- working declarations
- operational runbooks
- historical update reports
- internal request plans

## Public Rule
- public code and public docs must not depend on files inside the gitignored `doc/` tree
- if a policy concept is required for public understanding, summarize it in tracked public docs under `%OPENYGGDRASIL_ROOT%\\docs`
