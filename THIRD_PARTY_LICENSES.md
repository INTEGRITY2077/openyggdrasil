# Third-Party Licenses

## Purpose

This file records public third-party license notice for companion dependencies that are intentionally part of the OpenYggdrasil distribution surface.

This file currently documents the direct Graphify companion notice.

It does not yet claim to be a complete SBOM or a complete transitive dependency notice set.

## Direct Third-Party Notice

### Graphify

- Upstream project: `graphify`
- Upstream repository: <https://github.com/safishamsi/graphify>
- Reviewed upstream reference: `v4`
- Upstream package name: `graphifyy`
- Upstream license: MIT
- OpenYggdrasil usage: default-installed companion graph/query layer over the canonical vault

### OpenYggdrasil integration boundary

Graphify is currently used as a companion engine for:

- graph derivation
- graph query execution
- graph explain/path/query surface

Graphify is not treated as the OpenYggdrasil source of truth.

Canonical OpenYggdrasil memory remains in:

- `vault/`

OpenYggdrasil runtime wrappers currently live in:

- `projects/graphify-poc/`
- `providers/hermes/projects/harness/`

### Upstream copyright and license notice

Source: <https://github.com/safishamsi/graphify/blob/v4/LICENSE>

```text
MIT License

Copyright (c) 2026 Safi Shamsi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Scope Clarification

This notice covers the direct Graphify project notice that OpenYggdrasil must surface because Graphify is part of the intended default-installed companion path.

This file does not yet enumerate:

- every transitive package used by Graphify
- every optional extra dependency
- every runtime CDN or external API surface

Those remain separate review and packaging tasks.

## Packaging Rule

Any public OpenYggdrasil distribution that installs or bundles Graphify should preserve this notice or an equivalent notice carrying the same upstream attribution and license text.
