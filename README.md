# HyperView

> **Open-source dataset curation + embedding visualization (Euclidean + Poincaré disk)**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Hyper3Labs/HyperView) [![Open in HF Spaces](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/spaces/hyper3labs/HyperView)

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
- **Euclidean/Poincaré Toggle**: Switch between standard 2D UMAP and Poincaré disk visualization
- **HuggingFace Integration**: Load datasets directly from HuggingFace Hub
- **Fast Embeddings**: Uses EmbedAnything for CLIP-based image embeddings

## Updates

- **01-02-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop](https://www.meetup.com/berlin-computer-vision-group/events/312927919/) (Berlin Computer Vision Group)
- **17-01-26** — [The Geometry of Image Embeddings, Hands-on Coding Workshop, Part I](https://www.meetup.com/berlin-computer-vision-group/events/312636174/) (Berlin Computer Vision Group)

## Quick Start

**Docs:** [docs/datasets.md](docs/datasets.md) · [docs/colab.md](docs/colab.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [TESTS.md](TESTS.md)

### Installation

```bash
uv pip install hyperview
```

### Run the Demo

```bash
hyperview demo --samples 500
```

This will:
1. Load 500 samples from CIFAR-100
2. Compute CLIP embeddings
3. Generate Euclidean and Poincaré visualizations
4. Start the server at **http://127.0.0.1:6262**

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

## Contributing

Development setup, frontend hot-reload, and backend API notes live in [CONTRIBUTING.md](CONTRIBUTING.md).

## Related projects

- **hyper-scatter**: High-performance WebGL scatterplot engine (Euclidean + Poincaré) used by the frontend: https://github.com/Hyper3Labs/hyper-scatter
- **hyper-models**: Non-Euclidean model zoo + ONNX exports (e.g. for hyperbolic VLM experiments): https://github.com/Hyper3Labs/hyper-models

## References

- [Poincaré Embeddings for Learning Hierarchical Representations](https://arxiv.org/abs/1705.08039) (Nickel & Kiela, 2017)
- [Hyperbolic Neural Networks](https://arxiv.org/abs/1805.09112) (Ganea et al., 2018)

## License

MIT License - see [LICENSE](LICENSE) for details.
