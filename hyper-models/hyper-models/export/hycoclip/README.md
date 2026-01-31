# HyCoCLIP → ONNX export harness

This folder contains tooling to:

1. Run HyCoCLIP image embedding inference in PyTorch
2. Export the *image encoder path* to ONNX
3. Run ONNX inference via `onnxruntime`
4. Compare outputs (cosine similarity + max abs error)

Notes:
- HyCoCLIP code + weights are **not vendored** here.
- Upstream HyCoCLIP is CC-BY-NC; if you publish artifacts (e.g. ONNX weights), make sure you follow the upstream license and attribution requirements.

## Folder conventions

Expected local layout (recommended):

- `hycoclip_repo/` – a clone of https://github.com/PalAvik/hycoclip
- `checkpoints/` – downloaded `.pth` weights (e.g. `hycoclip_vit_s.pth`)
- `outputs/` – embeddings and exported ONNX artifacts

In the parent repo, large artifacts like `checkpoints/`, `outputs/`, and local virtualenvs are gitignored.

## Quickstart

### 0) Clone HyCoCLIP

```bash
cd "$(git rev-parse --show-toplevel)"/hyper_models/hycoclip_onnx

git clone https://github.com/PalAvik/hycoclip hycoclip_repo
```

### 1) Download a checkpoint

From upstream model zoo:

```bash
# Requires `huggingface-cli` configured.
# Alternatively just download manually from https://huggingface.co/avik-pal/hycoclip
huggingface-cli download avik-pal/hycoclip hycoclip_vit_s.pth --local-dir ./checkpoints
```

### 1.5) Create the local uv environment

This harness has its own `pyproject.toml` so you don’t need to add heavy deps to HyperView.

```bash
uv sync
```

### 2) Run torch inference

```bash
uv run python infer_torch.py \
  --hycoclip-repo ./hycoclip_repo \
  --checkpoint ./checkpoints/hycoclip_vit_s.pth \
  --variant vit_s \
  --image ../../assets/screenshot.png \
  --out ./outputs/torch_out.npz
```

### 3) Export ONNX

```bash
uv run python export_onnx.py \
  --hycoclip-repo ./hycoclip_repo \
  --checkpoint ./checkpoints/hycoclip_vit_s.pth \
  --variant vit_s \
  --onnx ./outputs/hycoclip_vit_s_image_encoder.onnx
```

Note: the exporter writes a paired weights file `hycoclip_vit_s_image_encoder.onnx.data` next to the `.onnx`. Keep both files together.

### 4) Run ONNX inference

```bash
uv run python infer_onnx.py \
  --onnx ./outputs/hycoclip_vit_s_image_encoder.onnx \
  --image ../../assets/screenshot.png \
  --out ./outputs/onnx_out.npz
```

### 5) Compare

```bash
uv run python compare_outputs.py \
  --torch ./outputs/torch_out.npz \
  --onnx  ./outputs/onnx_out.npz
```

## Troubleshooting notes

- **Export failures**: ViT attention export can be torch-version dependent. If export fails, try:
  - running on CPU (`--device cpu`)
  - a different torch version (PyTorch ONNX support changes quickly)
- **Preprocessing**: these scripts resize shortest side to 224 (bicubic), then center crop 224×224, then scale to `[0, 1]`.
  - HyCoCLIP normalizes internally using ImageNet mean/std (see upstream `hycoclip/models.py`).

## Publishing to Hugging Face (optional)

If you want to host exported ONNX models on the Hugging Face Hub, add a small wrapper repo that:

- Contains the `.onnx` + optional `.onnx.data` files
- Includes a model card with license/attribution

See `hf/` for a lightweight starting point.

