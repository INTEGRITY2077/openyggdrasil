# Runtime Provenance

`runtime/provenance/` owns provider-neutral provenance and temporal semantic
trace helpers.

## Responsibilities

- persist provenance records
- render and parse provenance pages
- preserve provider/session/source identity
- maintain semantic edge and temporal semantic edge artifacts
- keep source references attached to retrieval and lifecycle outputs

Provenance is the reason memory can be inspected later. A support bundle without
source/provenance evidence should be treated as weak or unavailable.
