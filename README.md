# HyperView

> **A scriptable embedding workbench for image dataset curation and model analysis**

HyperView turns an image dataset and a model into a live workspace: compute embeddings, project them into Euclidean, hyperbolic, or spherical layouts, inspect clusters and outliers, and keep samples, media, layouts, selections, and panels together across sessions.

It is built for ML/CV researchers, model builders, and coding agents who need a faster loop than notebooks plus screenshots and a more programmable surface than a fixed dashboard. The `hyperview` CLI controls the running UI, so a human or agent can create workspaces, run embedding/layout jobs, switch views, select samples, and install dataset-specific tools without editing the frontend.

Install it when a scatterplot is no longer enough: you want a local, extensible place to understand what your model grouped together, what it missed, and which samples deserve the next training or evaluation pass.

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

- **From image data to an embedding map.** Ingest images from Hugging Face or local folders, compute embeddings with built-in or custom providers, and persist samples, media, embedding spaces, and layouts for repeatable analysis.
- **Geometry-aware exploration.** Inspect the same dataset through Euclidean, Poincare/hyperbolic, and spherical views so hierarchy, clusters, outliers, and boundary cases are easier to see.
- **Curation primitives built into the workspace.** Browse linked thumbnails and labels, use click or lasso selection, query nearest neighbors, and keep the current working set visible while you reason about the data.
- **A CLI control plane for the live app.** Use `hyperview` commands to create workspaces, run jobs, switch layouts, set selections, and add panels while the UI stays open.
- **Agent-ready by default.** Install the HyperView skill and let coding agents operate the same workspace you are inspecting: select samples, call tools, change layouts, and report back with concrete IDs and artifacts.
- **Bring your own model or provider.** Register custom embedding providers, point HyperView at checkpoints, and compare the resulting spaces without rebuilding the app.
- **Dataset-specific tools and panels.** Add repo-local extensions with Python backend tools and native frontend panels, so a serious dataset can grow the exact analysis surface it needs.

## Updates

- **01-02-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop](https://www.meetup.com/berlin-computer-vision-group/events/312927919/) (Berlin Computer Vision Group)
- **17-01-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop, Part I](https://www.meetup.com/berlin-computer-vision-group/events/312636174/) (Berlin Computer Vision Group)
- **11-12-25** — [Hacker Room Demo Day #2](https://youtu.be/KnOiaNXN3Q0?t=2483) (Merantix AI Campus Berlin) — First version of HyperView presented

## Quick Start

**Docs:** [docs/datasets.md](docs/datasets.md) · [docs/colab.md](docs/colab.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [TESTS.md](TESTS.md)

### Install CLI and Skill

Install the HyperView CLI and refresh the agent skill in one copy-paste line:

```bash
uv tool install --python 3.12 --upgrade hyperview && hyperview skill install
```

HyperView currently supports Python 3.10 through 3.13; `--python 3.12` keeps the tool install on a widely supported runtime while upstream ML wheels catch up with newer Python releases. Re-running `hyperview skill install` replaces old HyperView skill copies, so the installed agent skill stays in sync with the upgraded CLI. By default this installs into detected agent locations plus the universal `~/.agents/skills/hyperview-cli` fallback. For a project-local Copilot install, run:

```bash
hyperview skill install --scope project --agent github-copilot --yes
```

In this repo the source skill lives at `.agents/skills/hyperview-cli/`, so contributors get the project skill just by opening the checkout. Use that skill before driving workspaces, embeddings, layouts, runtime panels, or plugins from an agent.

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

hyperview ui panel add \
  --workspace imagenette-demo \
  --panel-id model-a-poincare \
  --title "Model A" \
  --kind scatter \
  --layout-key <model-a-poincare-layout-key> \
  --position center

hyperview ui panel add \
  --workspace imagenette-demo \
  --panel-id model-b-poincare \
  --title "Model B" \
  --kind scatter \
  --layout-key <model-b-poincare-layout-key> \
  --position center \
  --reference-panel-id model-a-poincare \
  --direction right
```

Plugins use the same runtime path, but add Python tools too:

```bash
hyperview extension add .hyperview/extensions/selection-profile \
  --workspace imagenette-demo

hyperview tools run selection_profile.summarize \
  --workspace imagenette-demo \
  --param 'sample_ids=["sample-1","sample-8"]'
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
