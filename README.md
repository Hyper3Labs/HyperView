# HyperView

> Interactive geometric workbench for embedding space analysis.

HyperView turns image datasets into live embedding workspaces. Load samples, compute embeddings, inspect Euclidean, hyperbolic, or spherical layouts, select clusters and outliers, and keep media, labels, layouts, selections, panels, and tools in one local workspace.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Hyper3Labs/HyperView) [![Open in HF Spaces](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/spaces/hyper3labs/HyperView) [![Discord](https://img.shields.io/badge/Discord-hyper%C2%B3labs-5865F2?logo=discord&logoColor=white)](https://discord.gg/Za3rBkTPSf)

<p align="center">
  <a href="https://huggingface.co/spaces/hyper3labs/HyperView" target="_blank">
    <img src="https://raw.githubusercontent.com/Hyper3Labs/HyperView/main/assets/screenshot.png" alt="HyperView screenshot" width="100%">
  </a>
  <br>
  <a href="https://huggingface.co/spaces/hyper3labs/HyperView" target="_blank">Try the live demo on Hugging Face Spaces</a>
</p>

## Install

```bash
uv tool install --upgrade hyperview
hyperview skill install
```

For a project-local GitHub Copilot skill:

```bash
hyperview skill install --scope project --agent github-copilot --yes
```

## Python

```python
import hyperview as hv

dataset = hv.Dataset("cifar100")
dataset.add_from_huggingface("uoft-cs/cifar100", split="train", max_samples=1000)
dataset.compute_embeddings(model="openai/clip-vit-base-patch32")
dataset.compute_visualization()

hv.launch(dataset)
```

## CLI

```bash
hyperview workspace create imagenette-demo \
  --dataset imagenette_clip_20260411 \
  --activate

hyperview serve \
  --workspace imagenette-demo \
  --dataset imagenette_clip_20260411
```

Agents and scripts can control the running workspace:

```bash
hyperview ui layout set --workspace imagenette-demo --layout-key <layout-key>
hyperview ui selection set --workspace imagenette-demo --ids sample-1,sample-8
hyperview extension add .hyperview/extensions/selection-profile --workspace imagenette-demo
hyperview tools run selection_profile.summarize --workspace imagenette-demo
```

Export a prepared workspace as a read-only static demo that can be served by
Cloudflare Workers Static Assets without Python or a container:

```bash
hyperview export imagenette-demo --out dist/imagenette-demo
cd dist/imagenette-demo && npx wrangler deploy --config wrangler.jsonc
```

## What It Does

- Ingests image data from Hugging Face datasets or local folders.
- Computes embeddings with built-in or custom providers.
- Projects spaces into Euclidean, Poincare/hyperbolic, and spherical layouts.
- Links scatter points to thumbnails, labels, selections, and nearest neighbors.
- Adds dataset-specific Python tools and native frontend panels.
- Gives coding agents a CLI control plane for the same workspace humans inspect.

## Docs

- [Datasets](docs/datasets.md)
- [Static Spaces](docs/static-spaces.md)
- [Google Colab](docs/colab.md)
- [Contributing](CONTRIBUTING.md)
- [Testing and linting](CONTRIBUTING.md#testing--linting)

## Why Geometry?

Embedding failures often hide in the shape of the space: collapsed classes, weak separation, hierarchy, long-tail samples, and boundary cases. HyperView lets you inspect those structures through multiple geometric views instead of a single fixed projection.

## Related Projects

- [hyper-scatter](https://github.com/Hyper3Labs/hyper-scatter): WebGL scatterplot engine for Euclidean and Poincare views.
- [hyper-models](https://github.com/Hyper3Labs/hyper-models): Non-Euclidean model zoo and ONNX exports.
- [hyper-lrp](https://github.com/Hyper3Labs/hyper-lrp): Attribution tools for inspecting model evidence.

## Community

Join the [Hyper3Labs Discord](https://discord.gg/Za3rBkTPSf) for demos, setup help, and project discussion.

## License

MIT License. See [LICENSE](LICENSE).

## Citation

If you use HyperView in research, please cite:

```bibtex
@software{hyperview2026,
  author  = {{Hyper3Labs}},
  title   = {HyperView: An Interactive Geometric Workbench for Embedding Space Analysis},
  year    = {2026},
  version = {0.6.2},
  url     = {https://github.com/Hyper3Labs/HyperView}
}
```
