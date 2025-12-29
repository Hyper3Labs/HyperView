# HyperView

> **Open-source dataset curation with hyperbolic embeddings visualization - a FiftyOne alternative.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/HackerRoomAI/HyperView)

<div align="center">
  <a href="https://youtu.be/XLaa8FHSQtc" target="_blank">
    <img src="assets/screenshot.png" alt="HyperView Screenshot" style="width: 100%; max-width: 800px;">
  </a>
  <br>
  <a href="https://youtu.be/XLaa8FHSQtc" target="_blank">Watch the Demo Video</a>
</div>

---

## Features

- **Dual-Panel UI**: Image grid + scatter plot with bidirectional selection
- **Euclidean/Hyperbolic Toggle**: Switch between standard 2D UMAP and Poincaré disk visualization
- **HuggingFace Integration**: Load datasets directly from HuggingFace Hub
- **Fast Embeddings**: Uses EmbedAnything for CLIP-based image embeddings
- **FiftyOne-like API**: Familiar workflow for dataset exploration

## Quick Start

### Installation

```bash
pip install hyperview
```

Or install from source:

```bash
git clone https://github.com/HackerRoomAI/HyperView.git
cd HyperView
uv venv .venv
source .venv/bin/activate
uv pip install -e .
```

### Run the Demo

```bash
hyperview demo --samples 500
```

This will:

1. Load 500 samples from CIFAR-100
2. Compute CLIP embeddings
3. Generate Euclidean and Hyperbolic visualizations
4. Start the server at **http://127.0.0.1:5151**

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

# Compute embeddings and visualization
dataset.compute_embeddings()
dataset.compute_visualization()

# Launch the UI
hv.launch(dataset)  # Opens http://127.0.0.1:5151
```

## Why Hyperbolic?

Traditional Euclidean embeddings struggle with hierarchical data. In Euclidean space, volume grows polynomially ($r^d$), causing **Representation Collapse** where minority classes get crushed together.

**Hyperbolic space** (Poincaré disk) has exponential volume growth ($e^r$), naturally preserving hierarchical structure and keeping rare classes distinct.

![Euclidean vs Hyperbolic](assets/hyperview_infographic.png)

## Next Steps

- [Installation Guide](getting-started/installation.md)
- [Quick Start Tutorial](getting-started/quickstart.md)
- [Working with Datasets](guide/datasets.md)
- [Understanding Hyperbolic Space](concepts/hyperbolic.md)
- [Try the Interactive Demo](demo.md)

## References

- [Poincaré Embeddings for Learning Hierarchical Representations](https://arxiv.org/abs/1705.08039) (Nickel & Kiela, 2017)
- [Hyperbolic Neural Networks](https://arxiv.org/abs/1805.09112) (Ganea et al., 2018)
- [FiftyOne](https://github.com/voxel51/fiftyone) - Inspiration for the UI/API design

## License

MIT License - see [LICENSE](https://github.com/HackerRoomAI/HyperView/blob/main/LICENSE) for details.
