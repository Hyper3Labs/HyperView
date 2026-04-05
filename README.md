# HyperView

> **Open-source dataset curation + embedding visualization (Euclidean + Poincaré disk)**

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

- **Dual-Panel UI**: Image grid + scatter plot with bidirectional selection
- **Multi-Layout Visualizations**: Explore Euclidean, Poincare, and spherical layouts in 2D or 3D with UMAP or PCA projections
- **HuggingFace Integration**: Load datasets directly from HuggingFace Hub
- **Fast Embeddings**: Uses EmbedAnything for CLIP-based image embeddings

## Updates

- **01-02-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop](https://www.meetup.com/berlin-computer-vision-group/events/312927919/) (Berlin Computer Vision Group)
- **17-01-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop, Part I](https://www.meetup.com/berlin-computer-vision-group/events/312636174/) (Berlin Computer Vision Group)
- **11-12-25** — [Hacker Room Demo Day #2](https://youtu.be/KnOiaNXN3Q0?t=2483) (Merantix AI Campus Berlin) — First version of HyperView presented

## Quick Start

**Docs:** [docs/datasets.md](docs/datasets.md) · [docs/colab.md](docs/colab.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [TESTS.md](TESTS.md)

### Installation

```bash
uv pip install hyperview
```

### Run HyperView

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

This will:
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
