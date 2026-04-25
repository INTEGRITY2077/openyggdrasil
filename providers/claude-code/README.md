# Claude Code Provider

`claude-code` is the OpenYggdrasil provider surface for Claude Code and
Claude-compatible skill attachment.

OpenYggdrasil does not require a pre-bundled static adapter here. The
provider-facing surface is generated from repo-owned skill packaging and the
shared provider/session attachment contracts.

When the OpenYggdrasil skill is used inside Claude Code, the active provider
attachment is expected to be generated inside the workspace-local:

- `.yggdrasil/providers/claude-code/...`

## Phase 6 Packaging Baseline

Claude Code has a provider-native file deployment target in the repo-owned
skill deployer:

```text
.claude/skills/openyggdrasil/SKILL.md
```

Repo-owned deploy surface:

```text
runtime\attachments\deploy_skill.py
```

Activation path:

```text
.claude/skills/openyggdrasil/SKILL.md
```

Contract baseline:

- provider descriptor: `provider_descriptor.v1`
- session attachment: `session_attachment.v1`
- inbox binding: `inbox_binding.v1`
- turn delta: `turn_delta.v1`
- machine-readable baseline: `claude_code_provider_packaging_baseline.v1`

Expected workspace-local tree:

```text
.yggdrasil/providers/claude-code/<provider_profile>/<session_component>/provider_descriptor.v1.json
.yggdrasil/providers/claude-code/<provider_profile>/<session_component>/session_attachment.v1.json
.yggdrasil/providers/claude-code/<provider_profile>/<session_component>/inbox_binding.v1.json
.yggdrasil/providers/claude-code/<provider_profile>/<session_component>/turn_delta.v1.jsonl
.yggdrasil/inbox/claude-code/<provider_profile>/<session_component>.jsonl
```

Clean-room boundary:

- reference behavior and repo-owned packaging patterns only;
- do not copy, vendor, translate, or mechanically port local Claude Code
  implementation source;
- raw Claude Code sessions and transcripts are not copied into OpenYggdrasil;
- the inbox remains session-bound; no global inbox is allowed.

Known limitation:

- this baseline proves repo-owned provider-native file deployment and local
  attachment contracts, not current Claude Code product behavior.
