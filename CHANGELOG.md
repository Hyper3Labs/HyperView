# Changelog

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