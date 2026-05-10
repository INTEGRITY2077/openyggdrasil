# Claude Code Provider

`providers/claude-code/` documents the Claude Code attachment and packaging
baseline.

The public repository owns the openyggdrasil attachment contract and the
provider projection target. It does not copy, vendor, translate, or
mechanically port Claude Code implementation source.

The provider-native skill target is an install/projection target, not the
repo-managed Skill/MCP lifecycle source. Capability source and selection
metadata belong under `capabilities/` when that lifecycle is implemented.

## Public Baseline

- generated workspace artifacts: `.yggdrasil/providers/claude-code/...`
- provider-native skill target: `.claude/skills/openyggdrasil/SKILL.md`
- deploy/helper surface: `runtime/attachments/deploy_skill.py`
- machine-readable baseline:
  `contracts/claude_code_provider_packaging_baseline.v1.schema.json`

The skill target above must be tied back to a repo capability snapshot and
deployment receipt before it is considered managed.

## Required Contracts

- `provider_descriptor.v1`
- `session_attachment.v1`
- `inbox_binding.v1`
- `turn_delta.v1`

## Independent Attachment Boundary

- Public docs and contracts may reference product-level behavior.
- Private/reference source may inform behavior only through independent design notes and
  independently designed openyggdrasil contracts.
- Raw Claude Code sessions and transcripts are not copied into openyggdrasil.
- The inbox is session-bound; no global inbox is allowed.
