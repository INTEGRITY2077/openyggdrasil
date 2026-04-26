# Hermes Provider

`providers/hermes/` is the public Hermes adapter boundary.

Hermes is the most developed provider surface in this repository, but the
public repo still treats live foreground support conservatively: foreground
proof must be explicit, and foreground-equivalent fallback must not be relabeled
as live provider support.

## Public Shape

| Path | Role |
| --- | --- |
| `skills/` | Sanitized public manifest and boundary for the private provider-native skill bundle. |
| `projects/harness/` | Legacy Hermes harness compatibility surface currently still tracked in public. |
| `hooks/` | Public pointer for hook boundary documentation. |
| `memories/` | Public pointer for provider memory boundary documentation. |
| `policy/` | Public policy pointer, not the full internal policy corpus. |
| `vault/` | Compatibility pointer to the root `vault/`. |

Core runtime, contracts, canonical vault, and Graphify derivation live at the
repository root:

- `runtime/`
- `contracts/`
- `vault/`
- `common/graphify/`

## Attachment Baseline

- generated workspace artifacts: `.yggdrasil/providers/hermes/...`
- session inbox: `.yggdrasil/inbox/hermes/...`
- profile deployment helper:
  `runtime/attachments/deploy_hermes_profile_skill.py`
- machine-readable baseline:
  `contracts/hermes_provider_packaging_baseline.v1.schema.json`

Required contracts:

- `provider_descriptor.v1`
- `session_attachment.v1`
- `inbox_binding.v1`
- `turn_delta.v1`
- `hermes_foreground_unavailable_contract.v1`

## Current Limitations

- Live foreground support is recorded as typed unavailable until a checked
  foreground proof surface exists.
- Hermes background reasoning is typed and gated; an invocation marker alone is
  not a completed reasoning lease result.
- Provider raw sessions and transcripts are not copied into OpenYggdrasil.
- The inbox remains session-bound; no global inbox is allowed.
- Provider-native private bundles are not published in this public repository.
