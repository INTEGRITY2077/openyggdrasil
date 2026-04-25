# Runtime

This directory is reserved for core OpenYggdrasil runtime modules.

Expected future occupants:
- Amundsen family
- Gardener family
- Map Maker family
- Pathfinder family
- Tree Keeper family

Current occupants:
- common identity and runtime utilities
- provider-neutral decision capture, provider runtime integrity, and Decision Distiller runtime
- optional reasoning lease contract runtime
- promotion worthiness and placement runtime
- provenance and semantic edge runtime
- thin runner orchestration entrypoints
- pathfinder runtime and PTC MVP substrate
- skill-generated provider attachment runtime
- provider/session-bound reverse inbox runtime

## Runtime Surface Policy

Canonical implementations live under domain packages such as `runtime/admission/`, `runtime/delivery/`, `runtime/retrieval/`, and `runtime/attachments/`.

Same-name top-level modules are compatibility shims for legacy scripts, tests, and provider harnesses. They stay until provider imports migrate to canonical package paths and `runtime/import_smoke.py` confirms both surfaces remain importable.

Top-level modules without package counterparts are runtime utilities or proof entrypoints. They require an explicit policy decision before move/delete work.

See `runtime/shim_policy.py` for the executable mapping between compatibility shims and canonical targets.
