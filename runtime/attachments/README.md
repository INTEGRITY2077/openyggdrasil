# Runtime Attachments

`runtime/attachments/` owns provider-neutral attachment and bootstrap helpers.

## Responsibilities

- create, validate, and repair provider/session attachment artifacts
- bind provider sessions to session-scoped inbox paths
- append and read turn-delta artifacts
- run provider cold-start health checks
- deploy provider-native skill/bootstrap files where a provider supports them
- emit provider packaging baselines and known limitation matrices

## Public Boundary

Attachment helpers may create workspace-local `.yggdrasil/` artifacts, but they
must not copy raw provider transcripts into the public repository and must not
request provider credentials.

## Main Entry Points

- `validate_attachment.py`
- `repair_attachment.py`
- `provider_cold_start_healthcheck.py`
- `deploy_skill.py`
- `deploy_hermes_profile_skill.py`
