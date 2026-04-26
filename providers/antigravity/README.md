# Antigravity Provider

`providers/antigravity/` documents the Antigravity and Gemini-family attachment
baseline.

OpenYggdrasil does not ship a static Antigravity runtime bundle here. The
public baseline is generated from provider-neutral attachment contracts and
repo-owned bootstrap helpers.

## Public Baseline

- generated workspace artifacts: `.yggdrasil/providers/antigravity/...`
- generated Gemini-family file target: `GEMINI.md`
- deploy/helper surface: `runtime/attachments/deploy_skill.py`
- machine-readable baseline:
  `contracts/antigravity_provider_packaging_baseline.v1.schema.json`

## Required Contracts

- `provider_descriptor.v1`
- `session_attachment.v1`
- `inbox_binding.v1`
- `turn_delta.v1`

## Boundary

- Antigravity identity remains distinct from the Gemini generated file target.
- Raw Gemini or Antigravity sessions are not copied into OpenYggdrasil.
- The inbox is session-bound; no global inbox is allowed.
- This public folder is a documentation and packaging anchor, not a private
  provider bundle.
