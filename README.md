# HyperView

> **Open-source dataset curation + embedding visualization (Euclidean + Poincaré disk)**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Hyper3Labs/HyperView)

<p align="center">
  <a href="https://youtu.be/XLaa8FHSQtc" target="_blank">
    <img src="assets/screenshot.png" alt="HyperView Screenshot" width="100%">
  </a>
  <br>
  <a href="https://youtu.be/XLaa8FHSQtc" target="_blank">Watch the Demo Video</a>
</p>

---

## Features

- **Dual-Panel UI**: Image grid + scatter plot with bidirectional selection
- **Euclidean/Poincaré Toggle**: Switch between standard 2D UMAP and Poincaré disk visualization
- **HuggingFace Integration**: Load datasets directly from HuggingFace Hub
- **Fast Embeddings**: Uses EmbedAnything for CLIP-based image embeddings

## Quick Start

**Docs:** [docs/datasets.md](docs/datasets.md) · [docs/colab.md](docs/colab.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [TESTS.md](TESTS.md)

### Installation

```bash
git clone https://github.com/Hyper3Labs/HyperView.git
cd HyperView

# Install with uv
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
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

### Save and Load Datasets

```python
# Save dataset with embeddings
dataset.save("my_dataset.json")

# Load later
dataset = hv.Dataset.load("my_dataset.json")
hv.launch(dataset)
```

## Why Hyperbolic?

Traditional Euclidean embeddings struggle with hierarchical data. In Euclidean space, volume grows polynomially ($r^d$), causing **Representation Collapse** where minority classes get crushed together.

**Hyperbolic space** (Poincaré disk) has exponential volume growth ($e^r$), naturally preserving hierarchical structure and keeping rare classes distinct.

<p align="center">
  <img src="assets/hyperview_infographic.png" alt="Euclidean vs Hyperbolic" width="100%">
</p>

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
