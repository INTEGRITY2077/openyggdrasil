# Antigravity Provider

`antigravity` is the OpenYggdrasil provider surface for Antigravity workspace
attachment and the Gemini / Antigravity provider-family packaging path.

OpenYggdrasil does not require a pre-bundled static adapter here. The current
repo-owned baseline combines:

- `runtime\antigravity_router_bootstrap.py` for Antigravity workspace scaffold
  and local attachment bootstrap;
- `runtime\attachments\deploy_skill.py` for the Gemini-family `GEMINI.md`
  generated file target.

When the OpenYggdrasil skill is used inside Antigravity, the active provider
attachment is expected to be generated inside the workspace-local:

- `.yggdrasil/providers/antigravity/...`

## Phase 6 Packaging Baseline

Antigravity workspace scaffold paths:

```text
.agents/skills/openyggdrasil-provider-bootstrap/SKILL.md
.agents/rules/openyggdrasil-attachment-discipline.md
.agents/workflows/emit-openyggdrasil-bootstrap.md
```

Gemini-family generated file target:

```text
GEMINI.md
```

Contract baseline:

- provider descriptor: `provider_descriptor.v1`
- session attachment: `session_attachment.v1`
- inbox binding: `inbox_binding.v1`
- turn delta: `turn_delta.v1`
- machine-readable baseline: `antigravity_provider_packaging_baseline.v1`

Expected workspace-local tree:

```text
.yggdrasil/providers/antigravity/<provider_profile>/<session_component>/provider_descriptor.v1.json
.yggdrasil/providers/antigravity/<provider_profile>/<session_component>/session_attachment.v1.json
.yggdrasil/providers/antigravity/<provider_profile>/<session_component>/inbox_binding.v1.json
.yggdrasil/providers/antigravity/<provider_profile>/<session_component>/turn_delta.v1.jsonl
.yggdrasil/inbox/antigravity/<provider_profile>/<session_component>.jsonl
```

Safety boundary:

- this baseline proves repo-owned Gemini file generation and Antigravity
  workspace scaffold behavior, not current product behavior;
- Antigravity provider identity remains distinct from the Gemini file target;
- raw Gemini or Antigravity sessions and transcripts are not copied;
- the inbox remains session-bound; no global inbox is allowed.
