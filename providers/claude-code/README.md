# Claude Code Provider

`providers/claude-code/` documents the Claude Code attachment and packaging
baseline.

The public repository owns the OpenYggdrasil attachment contract and skill
deployment target. It does not copy, vendor, translate, or mechanically port
Claude Code implementation source.

## Public Baseline

- generated workspace artifacts: `.yggdrasil/providers/claude-code/...`
- provider-native skill target: `.claude/skills/openyggdrasil/SKILL.md`
- deploy/helper surface: `runtime/attachments/deploy_skill.py`
- machine-readable baseline:
  `contracts/claude_code_provider_packaging_baseline.v1.schema.json`

## Required Contracts

- `provider_descriptor.v1`
- `session_attachment.v1`
- `inbox_binding.v1`
- `turn_delta.v1`

## Clean-Room Boundary

- Public docs and contracts may reference product-level behavior.
- Private/reference source may inform behavior only through clean-room notes and
  independently designed OpenYggdrasil contracts.
- Raw Claude Code sessions and transcripts are not copied into OpenYggdrasil.
- The inbox is session-bound; no global inbox is allowed.
