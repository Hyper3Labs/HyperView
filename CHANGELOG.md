# Changelog

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