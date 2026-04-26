# Common Graphify Derivation

This directory contains the provider-neutral Graphify derivation stack for
OpenYggdrasil. Graphify is a common support stack, not a Hermes-specific
provider surface.

## Role

- stage canonical notes from `%OPENYGGDRASIL_ROOT%\vault`
- derive structural graph artifacts with Graphify
- expose query, path, and explain wrappers over derived graph output

## Canonical Paths

- manifest:
  - `%OPENYGGDRASIL_ROOT%\common\graphify-poc\graphify-corpus.manifest.json`
- query wrapper:
  - `%OPENYGGDRASIL_ROOT%\common\graphify-poc\query_graphify.py`
- pipeline wrapper:
  - `%OPENYGGDRASIL_ROOT%\common\graphify-poc\run_graphify_pipeline.py`
- implementation:
  - `%OPENYGGDRASIL_ROOT%\common\graphify-poc\*.py`

## Boundary

Graphify output is derived navigation/reporting material, not SOT. Providers
must verify answers against canonical vault/source references before using graph
output in a response.
