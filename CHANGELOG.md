# Changelog

## 0.4.2 - 2026-05-11

### Fixes
- Prevent project-scope skill installs from deleting the repo-local `.agents/skills/hyperview-cli` source directory when source and destination are the same path.
- Cap supported Python metadata at `<3.14` and document `uv tool install --python 3.12` while upstream ML dependency wheels are unavailable for Python 3.14.

## 0.4.1 - 2026-05-10

### Fixes
- Report the installed package version from the HyperView health endpoint instead of the stale hardcoded server version.

## 0.4.0 - 2026-05-10

### Features
- Add the packaged `hyperview skill install` workflow for refreshing the HyperView agent skill across supported coding agents.
- Add runtime scatter panels that can be bound to explicit layout keys for side-by-side embedding comparisons.
- Add project-local extension discovery from the nearest `.hyperview/extensions` directory.

### Improvements
- Update the frontend to use `hyper-scatter` 0.4.0 and explicit Poincare pan anchors.
- Strengthen installer safeguards for custom skill destinations.
- Keep streaming Hugging Face ingestion working for iterable datasets without private fingerprints.

### Breaking Changes
- Remove the legacy top-level one-shot CLI flow; use explicit control-plane commands such as `hyperview dataset create`, `hyperview workspace create`, and `hyperview serve`.
- Reject unsupported persisted LanceDB layout registry schemas instead of silently rebuilding them.

## 0.3.1 - 2026-03-22

### Fixes
- Switch the frontend `hyper-scatter` dependency to the published npm package so clean installs and GitHub release builds resolve it without a local checkout.

### Notes
- This release supersedes the failed `0.3.0` PyPI publish and carries forward the user-facing changes documented below.

## 0.3.0 - 2026-03-22

### Features
- Add PCA projection support for Euclidean, Poincare, and spherical visualization layouts.
- Add 3D layout support for visualizations, including spherical views and 3D lasso selection.
- Add Hugging Face ingestion controls for subset configs, streaming, and configurable shuffle buffers.

### Improvements
- Preserve stable source indices and requested sample tracking during Hugging Face ingestion.
- Expand the demo workflow with ready-made Euclidean, Poincare, spherical, and PCA layouts.

### Breaking Changes
- Replace CLI `--geometry` with repeatable `--layout` flags such as `--layout euclidean`, `--layout poincare`, and `--layout spherical`.
- Replace `Dataset.compute_visualization(geometry=...)` with `Dataset.compute_visualization(layout=...)`; bare `spherical` layouts now resolve to 3D.