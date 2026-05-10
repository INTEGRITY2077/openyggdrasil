# Hermes Skill Bundle Boundary

This directory is the public boundary for the Hermes provider-native skill
bundle.

The full provider-native bundle is private development capital and is not
published in this repository.

This directory is not the Skill lifecycle source of truth. Hermes-installed
OpenYggdrasil skills are provider-local projection/install artifacts. The
planned repo-managed source/control plane for Skill, MCP, tool, and TST
worker-manual lifecycle management is `capabilities/`.

An installed Hermes `SKILL.md` copy is managed only when it can be tied back to
a repo capability snapshot, provider-specific projection, deployment receipt,
and drift check.

## Public Contents

- sanitized boundary README
- `public_manifest.v1.json`
- runtime code elsewhere that can consume a private bundle supplied out of band

## Forbidden Public Contents

- raw skill implementations
- red-team templates
- credential helpers
- private workflow prompts
- bundled third-party operational material
- provider raw sessions or transcripts

## Nonclaims

- This directory does not claim current local Hermes skill installs are clean.
- This directory does not claim Hermes curator manages OpenYggdrasil local
  skills.
- This directory does not authorize copying one user's `~/.hermes/skills`
  directory as the distribution source for other users.
