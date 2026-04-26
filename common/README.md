# Common

`common/` contains provider-neutral support stacks that are required by more
than one provider but are not core runtime packages.

Current stack:

- `graphify/`: non-SOT graph/wiki/index derivation over canonical vault
  material.

Common stacks must not own provider authentication, raw provider sessions,
canonical vault writes, or provider-specific private bundles.
