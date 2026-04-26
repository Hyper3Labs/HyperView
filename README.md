# HyperView

> **An embedding visualizer for agents, plugins, and model analysis**

HyperView is an embedding visualizer for image and multimodal datasets. Use it to inspect clusters, labels, nearest neighbors, and model behavior across Euclidean, hyperbolic, and spherical spaces.

The CLI controls the app. Agents can create workspaces, compute embeddings and layouts, switch the visible UI, select samples, and install plugins with backend tools plus native frontend panels. That means a visualization can be shaped around the dataset, not locked into one fixed dashboard.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Hyper3Labs/HyperView) [![Open in HF Spaces](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/spaces/hyper3labs/HyperView) [![Discord](https://img.shields.io/badge/Discord-hyper%C2%B3labs-5865F2?logo=discord&logoColor=white)](https://discord.gg/Za3rBkTPSf)

<p align="center">
  <a href="https://huggingface.co/spaces/hyper3labs/HyperView" target="_blank">
    <img src="https://raw.githubusercontent.com/Hyper3Labs/HyperView/main/assets/screenshot.png" alt="HyperView Screenshot" width="100%">
  </a>
  <br>
  <a href="https://huggingface.co/spaces/hyper3labs/HyperView" target="_blank">Try the live demo on HuggingFace Spaces</a>
</p>

---

## Features

- CLI-controlled UI. Use `hyperview` to create workspaces, compute layouts, change the visible panel, and select samples in the running app. Agents can drive the same app humans see.
- Fast embeddings and nearest neighbors. Compute embeddings with built-in or custom providers, persist them per dataset, and query similarity from the runtime API.
- One dataset per workspace. A workspace has one active dataset, its computed spaces, its selected layout, its current selection, and its panels.
- Plugins with backend and frontend. Install a local extension folder with `extension.toml`, Python tools, and a native React panel. The panel can call its backend tools through the shared HyperView panel SDK.
- Bespoke visualization workbenches. Add dataset-specific panels, providers, tools, and layouts without touching frontend source. Every serious dataset can get the view it needs.

## Updates

- **01-02-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop](https://www.meetup.com/berlin-computer-vision-group/events/312927919/) (Berlin Computer Vision Group)
- **17-01-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop, Part I](https://www.meetup.com/berlin-computer-vision-group/events/312636174/) (Berlin Computer Vision Group)
- **11-12-25** — [Hacker Room Demo Day #2](https://youtu.be/KnOiaNXN3Q0?t=2483) (Merantix AI Campus Berlin) — First version of HyperView presented

## Quick Start

**Docs:** [docs/datasets.md](docs/datasets.md) · [docs/colab.md](docs/colab.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [TESTS.md](TESTS.md)

### Install CLI and Skill

Install the HyperView CLI first:

```bash
uv pip install hyperview
```

Then make the HyperView agent skill available to your coding agent. In this repo it lives at:

```text
.agents/skills/hyperview-cli/
```

Use that skill before driving workspaces, embeddings, layouts, runtime panels, or plugins from an agent.

### Run HyperView

Create a workspace, bind one dataset to it, and drive the running app from the CLI.

```bash
hyperview workspace create imagenette-demo \
  --dataset imagenette_clip_20260411 \
  --activate

hyperview serve \
  --workspace imagenette-demo \
  --dataset imagenette_clip_20260411 \
  --no-browser
```

Then change the live UI from the CLI:

```bash
hyperview ui layout set \
  --workspace imagenette-demo \
  --layout-key <layout-key>

hyperview ui panel add \
  --workspace imagenette-demo \
  --panel-id labels \
  --title "Labels" \
  --position right \
  --module-file agent-context/panels/labels/panel.jsx
```

Plugins use the same runtime path, but add Python tools too:

```bash
hyperview extension add agent-context/extensions/selection-profile \
  --workspace imagenette-demo

hyperview tools run selection_profile.summarize \
  --workspace imagenette-demo \
  --param 'sample_ids=["sample-1","sample-8"]'
```

Legacy one-shot launch is still available for quick experiments:

```bash
hyperview \
  --dataset cifar10_demo \
  --hf-dataset uoft-cs/cifar10 \
  --split train \
  --image-key img \
  --label-key label \
  --samples 500 \
  --model openai/clip-vit-base-patch32 \
  --layout euclidean \
  --layout poincare
```

This legacy flow will:
1. Use dataset `cifar10_demo`
2. Load up to 500 samples from CIFAR-10
3. Compute CLIP embeddings
4. Generate Euclidean and Poincare visualizations
5. Start the server at **http://127.0.0.1:6262**

You can also launch with explicit dataset/model/projection args:

```bash
hyperview \
  --dataset imagenette_clip \
  --hf-dataset fastai/imagenette \
  --split train \
  --image-key image \
  --label-key label \
  --samples 1000 \
  --model openai/clip-vit-base-patch32 \
  --method umap \
  --layout euclidean
```

### Python API

```python
import hyperview as hv

# Create dataset
dataset = hv.Dataset("my_dataset")

# Load from HuggingFace
dataset.add_from_huggingface(
    "uoft-cs/cifar100",
    split="train",
    max_samples=1000
)

# Or load from local directory
# dataset.add_images_dir("/path/to/images", label_from_folder=True)

# Compute embeddings and visualization
dataset.compute_embeddings(model="openai/clip-vit-base-patch32")
dataset.compute_visualization()

# Launch the UI
hv.launch(dataset)  # Opens http://127.0.0.1:6262
```

### Google Colab

See [docs/colab.md](docs/colab.md) for a fast Colab smoke test and notebook-friendly launch behavior.

## Why Hyperbolic?

Traditional Euclidean embeddings struggle with hierarchical data. In Euclidean space, volume grows polynomially ($r^d$), causing **[Representation Collapse](https://hyper3labs.github.io/collapse)** where minority classes get crushed together.

**[Hyperbolic space](https://hyper3labs.github.io/warp)** (Poincaré disk) has exponential volume growth ($e^r$), naturally preserving hierarchical structure and keeping rare classes distinct.

**[Try the live demo on HuggingFace Spaces→](https://huggingface.co/spaces/hyper3labs/HyperView)**

## Community

**Weekly Open Discussion** — Every Tuesday at 15:00 UTC on [Discord](https://discord.gg/Az7k4Ure?event=1469730571440885944)

Join us to see the latest features demoed live, walk through new code, and get help with local setup. Whether you're a core maintainer or looking for your first contribution, everyone is welcome.

## Contributing

Development setup, frontend hot-reload, and backend API notes live in [CONTRIBUTING.md](CONTRIBUTING.md).

## Related projects

- **hyper-scatter**: High-performance WebGL scatterplot engine (Euclidean + Poincaré) used by the frontend: https://github.com/Hyper3Labs/hyper-scatter
- **hyper-models**: Non-Euclidean model zoo + ONNX exports : https://github.com/Hyper3Labs/hyper-models

## License

MIT License - see [LICENSE](LICENSE) for details.


## Citation

If you use HyperView in your research, please cite:
```bibtex
@software{hyperview2025,
  author  = {Mahmood, Matin and Rueda-Toicen, Antonio and Morozov, Daniil},
  title   = {HyperView: Open-source Dataset Curation and Model Analysis},
  year    = {2025},
  url     = {https://github.com/Hyper3Labs/HyperView/tree/main}
}
```
