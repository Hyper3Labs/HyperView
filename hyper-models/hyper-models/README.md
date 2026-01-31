# hyper-models

<p align="center">
  <strong>A model zoo for non-Euclidean embedding models</strong>
  <br>
  <em>Hyperbolic · Spherical · Product Manifolds</em>
</p>

<p align="center">
  <a href="https://huggingface.co/mnm-matin/hyperbolic-clip">
    <img src="https://img.shields.io/badge/🤗_Models-hyperbolic--clip-orange" alt="Hugging Face">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue" alt="License: MIT">
  </a>
</p>

---

## Why?

- **Standardized access** to non-Euclidean embedding models
- **Torch-free runtime** via ONNX (models published to Hugging Face Hub)
- **Simple API** — `load()` and `encode_images()`

## Installation

```bash
pip install hyper-models
```

## Usage

```python
import hyper_models
from PIL import Image

# List available models
hyper_models.list_models()
# ['hycoclip-vit-s', 'hycoclip-vit-b', 'meru-vit-s', 'meru-vit-b']

# Load model (auto-downloads from Hugging Face Hub)
model = hyper_models.load("hycoclip-vit-s")
model.geometry  # 'hyperboloid'
model.dim       # 513

# Encode PIL images
images = [Image.open("image.jpg")]
embeddings = model.encode_images(images)  # (1, 513) ndarray

# Get model info
info = hyper_models.get_model_info("hycoclip-vit-s")
info.hub_id     # 'mnm-matin/hyperbolic-clip'
info.license    # 'CC-BY-NC'

# Low-level: preprocess images yourself
batch = hyper_models.preprocess_images(images)  # (B, 3, 224, 224)
embeddings = model.encode(batch)
```

## Models

### Hyperbolic

| Model | Available | Paper | Code |
|-------|:---------:|-------|------|
| `hycoclip-vit-s` | [![HF](https://img.shields.io/badge/🤗-HuggingFace-yellow)](https://huggingface.co/mnm-matin/hyperbolic-clip/tree/main/hycoclip-vit-s) | [ICLR 2025](https://arxiv.org/abs/2410.06912) | [PalAvik/hycoclip](https://github.com/PalAvik/hycoclip) |
| `hycoclip-vit-b` | [![HF](https://img.shields.io/badge/🤗-HuggingFace-yellow)](https://huggingface.co/mnm-matin/hyperbolic-clip/tree/main/hycoclip-vit-b) | [ICLR 2025](https://arxiv.org/abs/2410.06912) | [PalAvik/hycoclip](https://github.com/PalAvik/hycoclip) |
| `meru-vit-s` | [![HF](https://img.shields.io/badge/🤗-HuggingFace-yellow)](https://huggingface.co/mnm-matin/hyperbolic-clip/tree/main/meru-vit-s) | [ICML 2023](https://arxiv.org/abs/2304.09172) | [facebookresearch/meru](https://github.com/facebookresearch/meru) |
| `meru-vit-b` | [![HF](https://img.shields.io/badge/🤗-HuggingFace-yellow)](https://huggingface.co/mnm-matin/hyperbolic-clip/tree/main/meru-vit-b) | [ICML 2023](https://arxiv.org/abs/2304.09172) | [facebookresearch/meru](https://github.com/facebookresearch/meru) |
| `hyp-vit` | — | [CVPR 2022](https://arxiv.org/abs/2203.10833) | [htdt/hyp_metric](https://github.com/htdt/hyp_metric) |
| `hie` | — | [CVPR 2020](https://arxiv.org/abs/1904.02239) | [leymir/hyperbolic-image-embeddings](https://github.com/leymir/hyperbolic-image-embeddings) |
| `hcnn` | — | [ICLR 2024](https://openreview.net/forum?id=ekz1hN5QNh) | [kschwethelm/HyperbolicCV](https://github.com/kschwethelm/HyperbolicCV) |

### Spherical

| Model | Available | Paper | Code |
|-------|:---------:|-------|------|
| `sphereface` | — | [CVPR 2017](https://arxiv.org/abs/1704.08063) | [wy1iu/sphereface](https://github.com/wy1iu/sphereface) |
| `arcface` | — | [CVPR 2019](https://arxiv.org/abs/1801.07698) | [deepinsight/insightface](https://github.com/deepinsight/insightface) |

### Product Manifolds

| Model | Available | Paper | Code |
|-------|:---------:|-------|------|
| `hyperbolics` | — | [ICLR 2019](https://openreview.net/forum?id=HJxeWnCcF7) | [HazyResearch/hyperbolics](https://github.com/HazyResearch/hyperbolics) |

## Export Tooling

This repo also contains tooling to export PyTorch models to ONNX:

```bash
cd export/hycoclip
uv run python export_onnx.py --checkpoint model.pth --onnx model.onnx
```

See [export/hycoclip/README.md](export/hycoclip/README.md) for details.

## References

- [HyCoCLIP](https://github.com/PalAvik/hycoclip)
- [MERU](https://github.com/facebookresearch/meru)
- [geoopt](https://github.com/geoopt/geoopt)
