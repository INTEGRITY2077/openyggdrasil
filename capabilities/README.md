# Capability Lifecycle

`capabilities/` is the planned public source/control plane for
openyggdrasil Skill, MCP, tool, and TST worker-manual management.

Provider-local files are not the source of truth. A local Hermes
`~/.hermes/skills/openyggdrasil-*` directory, a Claude Code skill install, or a
provider MCP config is a user-local projection/install artifact. It may be
inspected for drift, but it must not be used as the release source for other
users.

Hermes itself is an important clean-room provider-runtime reference for
OpenYggdrasil skill, MCP, toolset, reload, curator, and native pane behavior.
That makes Hermes a reference baseline to learn from, not the OpenYggdrasil
release source. Local Hermes installs remain projection artifacts unless a
repo capability snapshot and deployment receipt prove otherwise.

## Distribution Model

Managed distribution is source-to-projection:

```text
setup skill / installer
-> active capability root
-> validated capability snapshot
-> provider-specific projection package
-> user-local install/update
-> deployment receipt
-> drift check
-> rollback target
```

The default active capability root is the repository-provided default. Advanced
users may switch to a local or external capability root, but the active root
must be recorded and validated before it can produce a snapshot.

The capability snapshot is the release unit. User-local provider artifacts are
derived from that snapshot and must leave deployment evidence.

## Planned Tree

```text
capabilities/
  defaults/
    schema/
    registry/
    snapshots/
    skills/
    mcp/
    tools/
    overlays/

  local/
    README.md

  config/
    capability_root.v1.json

  registry/
    capability_registry.v1.json
    snapshots/
    deployment_receipts/

  skills/
    hermes_collaboration/
      provider/
      postman/
      memory_saver/
      memory_finder/
      shared/
    tst_worker/
      memory_saver/
      memory_finder/
      shared/

  mcp/
    toolsets/
    adapters/
    server_profiles/

  tools/
    ptc/
    tst_selectors/
    retrieval_generators/
    evaluators/

  overlays/
    defaults/
    user_preferences.schema.json

  projections/
    hermes/
    codex/
    claude_code/
```

This tree is a management contract. Empty or missing subdirectories do not mean
the capability is implemented.

## Setup Defaults And Movable Roots

Default setup should be automatic:

```text
bootstrap skill
-> setup skill / installer
-> load capabilities/defaults
-> create or validate active capability root
-> build snapshot
-> project into provider target
-> install
-> write deployment receipt
```

The user should not need to hand-edit capability files to get the default
OpenYggdrasil behavior.

If a user wants separate management, the active root can move:

```text
root_mode: default | local_override | external
default_root: capabilities/defaults
local_root: capabilities/local
external_root: user-provided path
active_root: resolved root used for snapshot generation
fallback_root: capabilities/defaults
```

Root movement changes where source is read from. It does not change the rules:
hard nonclaims, product safety defaults, evidence requirements, and deployment
receipts remain mandatory.

## Two Skill Planes

Openyggdrasil separates two skill planes:

| Plane | Runtime surface | Purpose | Source of truth |
| --- | --- | --- | --- |
| Hermes collaboration skills | Provider-native Hermes skill projection | Provider, Postman, Memory Saver, and Memory Finder cooperation inside Hermes | Repo capability source plus deployment receipt |
| OY TST worker skills | TST catalog and worker manuals | Memory Saver/Finder capability selection, PTC execution, retry, evaluation, and receipt shaping | Repo capability source and catalog snapshot |

Do not collapse these planes. Putting Memory Saver/Finder worker manuals into a
Provider-facing skill pollutes the Provider surface. Treating installed provider
skills as product source creates drift.

## Capability Records

A capability record should be able to describe:

```text
capability_family
role_target
skill_plane
source_ref
source_hash
adapter_status
projection_targets
deployment_receipt_ref
required_evidence_refs
hard_nonclaims
preference_overlay_refs
evolution_policy
```

These records are what TST should select from. TST must not invent capabilities
from a provider prompt or from user-local installed files.

## Deployment Receipts

An install/update is managed only when it records evidence such as:

```text
snapshot_id
source_hash
projection_hash
installed_artifact_hash
target_provider
target_path
installed_at
drift_status
rollback_target
```

An installed artifact without a deployment receipt is unmanaged local state.

## Preference Overlay

User preference history belongs in overlay records, not pasted into every
Provider-facing skill body.

Examples:

```text
provider_surface_quietness
worker_surface_visibility
evidence_strictness
naming_alignment
retry_behavior
memory_recall_style
```

The ranking order is:

```text
hard safety / hard nonclaims
> mission contract
> role boundary
> evidence contract
> user preference overlay
> heuristic ranking
```

An overlay may guide selection or projection. It must not override hard rules.

## Skill Evolution

Skill evolution is reviewable and reversible:

```text
observe
-> propose
-> verify
-> promote
-> deploy
-> drift-check
-> rollback
```

Self-evolving skill does not mean silent mutation of a live provider install.
Observed failures or user corrections may create patch candidates, preference
overlay updates, or verification fixtures. They do not directly edit the
installed Provider skill as product truth.

## Nonclaims

This directory does not claim:

```text
all-user installer implementation
Hermes projection compiler implementation
real MCP adapter execution
current local Hermes skills are clean or managed
provider-neutral Tool Search Tool parity
production readiness
```
